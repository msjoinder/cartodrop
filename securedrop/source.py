# -*- coding: utf-8 -*-
import os
from datetime import datetime
import uuid
from functools import wraps

from flask import (Flask, request, render_template, session, redirect, url_for,
                   flash, abort, g, send_file)
from flask_wtf.csrf import CsrfProtect

import config
import version
import crypto_util
import store
import background
import zipfile
from cStringIO import StringIO
import mapper, json, db

app = Flask(__name__, template_folder=config.SOURCE_TEMPLATES_DIR)
app.config.from_object(config.FlaskConfig)
CsrfProtect(app)

app.jinja_env.globals['version'] = version.__version__
if getattr(config, 'CUSTOM_HEADER_IMAGE', None):
    app.jinja_env.globals['header_image'] = config.CUSTOM_HEADER_IMAGE
    app.jinja_env.globals['use_custom_header_image'] = True
else:
    app.jinja_env.globals['header_image'] = 'securedrop.png'
    app.jinja_env.globals['use_custom_header_image'] = False


def logged_in():
    if 'logged_in' in session:
        return True


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not logged_in():
            return redirect(url_for('lookup'))
        return f(*args, **kwargs)
    return decorated_function


def ignore_static(f):
    """Only executes the wrapped function if we're not loading a static resource."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.path.startswith('/static'):
            return  # don't execute the decorated function
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
@ignore_static
def setup_g():
    """Store commonly used values in Flask's special g object"""
    # ignore_static here because `crypto_util.shash` is bcrypt (very time consuming),
    # and we don't need to waste time running if we're just serving a static
    # resource that won't need to access these common values.
    if logged_in():
        g.flagged = session['flagged']
        g.codename = session['codename']
        g.sid = crypto_util.shash(g.codename)
        g.loc = store.path(g.sid)


@app.before_request
@ignore_static
def check_tor2web():
        # ignore_static here so we only flash a single message warning about Tor2Web,
        # corresponding to the intial page load.
    if 'X-tor2web' in request.headers:
        flash('<strong>WARNING:</strong> You appear to be using Tor2Web. '
              'This <strong>does not</strong> provide anonymity. '
              '<a href="/tor2web-warning">Why is this dangerous?</a>',
              "header-warning")


@app.after_request
def no_cache(response):
    """Minimize potential traces of site access by telling the browser not to
    cache anything"""
    no_cache_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '-1',
    }
    for header, header_value in no_cache_headers.iteritems():
        response.headers.add(header, header_value)
    return response

@app.route('/')
def home():
    stories = []

    dirs = os.listdir(config.STORY_STORE_DIR)
    for d in dirs:
        display_id = d
        stories.append(dict(
            name=d,
            sid=display_id,
            date=str(datetime.fromtimestamp(os.stat(os.path.join(config.STORY_STORE_DIR, d)).st_mtime)
                     ).split('.')[0]
        ))

    stories.sort(key=lambda x: x['date'], reverse=True)
    return render_template('home.html', stories=stories)

@app.route('/post')
def index():
    return render_template('index.html')


@app.route('/generate', methods=('GET', 'POST'))
def generate():
    number_words = 8
    if request.method == 'POST':
        number_words = int(request.form['number-words'])
        if number_words not in range(7, 11):
            abort(403)
    session['codename'] = crypto_util.genrandomid(number_words)
    return render_template('generate.html', codename=session['codename'])


@app.route('/create', methods=['POST'])
def create():
    sid = crypto_util.shash(session['codename'])
    if os.path.exists(store.path(sid)):
        # if this happens, we're not using very secure crypto
        store.log("Got a duplicate ID '%s'" % sid)
    else:
        os.mkdir(store.path(sid))
    session['logged_in'] = True
    session['flagged'] = False
    return redirect(url_for('lookup'))


@app.route('/lookup', methods=('GET',))
@login_required
def lookup():
    msgs = []
    flagged = False
    for fn in os.listdir(g.loc):
        if fn == '_FLAG':
            flagged = True
            continue
        if fn.startswith('reply-'):
            msgs.append(dict(
                id=fn,
                date=str(
                    datetime.fromtimestamp(
                        os.stat(store.path(g.sid, fn)).st_mtime)),
                msg=crypto_util.decrypt(
                    g.sid, g.codename, file(store.path(g.sid, fn)).read())
            ))
    if flagged:
        session['flagged'] = True

    def async_genkey(sid, codename):
        with app.app_context():
            background.execute(lambda: crypto_util.genkeypair(sid, codename))

    # Generate a keypair to encrypt replies from the journalist
    # Only do this if the journalist has flagged the source as one
    # that they would like to reply to. (Issue #140.)
    if not crypto_util.getkey(g.sid) and flagged:
        async_genkey(g.sid, g.codename)

    outimg = None
    outlabels = []
    if os.path.exists(g.sid + '.geojson'):
        map_gj = mapper.get_my_geojson(g.sid)
        outimg = map_gj["img"]
        outlabels = map_gj["labels"]

    return render_template(
        'lookup.html', codename=g.codename, msgs=msgs, flagged=flagged,
        haskey=crypto_util.getkey(g.sid), outimg=outimg, outlabels=outlabels)

@app.route('/story/<sid>', methods=('GET',))
def story(sid):
    outimg = None
    outlabels = []
    if os.path.exists( os.path.join(config.STORY_STORE_DIR, sid, sid + '.geojson') ):
        map_gj = mapper.get_my_geojson(sid, True)
        outimg = map_gj["img"]
        outlabels = map_gj["labels"]

    return render_template('story.html', outimg=outimg, outlabels=outlabels)

@app.route('/submit', methods=('POST',))
@login_required
def submit():
    msg = request.form['msg']
    lat_str = request.form['lat'].upper()
    lng_str = request.form['lng'].upper()
    fh = request.files['fh']

    if msg:
        msg_loc = store.path(g.sid, '%s_msg.gpg' % uuid.uuid4())
        crypto_util.encrypt(config.JOURNALIST_KEY, msg, msg_loc)
        flash("Thanks! We received your message.", "notification")

    if lat_str and lng_str:
        # parse lat and lng
        lat = float(lat_str.replace('N','').replace('S','').replace('E','').replace('W',''))
        lng = float(lng_str.replace('N','').replace('S','').replace('E','').replace('W',''))
        
        # positive/negative coordinates
        if (lat_str.find('N') > -1 and lat < 0) or (lat_str.find('S') > -1 and lat > 0):
            lat = lat * -1
        if (lng_str.find('E') > -1 and lng < 0) or (lng_str.find('W') > -1 and lng > 0):
            lng = lng * -1

        # generate GeoJSON
        geojson = None
        uploadFeature = {
            "type": "Feature",
            "properties": {
                "msg": msg
            },
            "geometry": {
                "type": "Point",
                "coordinates": [ float(lng), float(lat) ]
            }
        }
        if os.path.exists(g.sid + '.geojson'):
            currentfile = open(g.sid + '.geojson', 'r')
            geojson = json.load(currentfile)
            currentfile.close()
            uploadFeature["properties"]["sort_id"] = len(geojson["features"]) + 1
            geojson["features"].append(uploadFeature)
        else:
            uploadFeature["properties"]["sort_id"] = 1
            geojson = {
                "type": "FeatureCollection",
                "features": [uploadFeature]
            }
        gjfile = open(g.sid + '.geojson', 'w')
        gjfile.write( json.dumps( geojson ) )
        gjfile.close()
        
        # store lat/lng feature
        ll = json.dumps( uploadFeature )
        ll_loc = store.path(g.sid, '%s_ll.gpg' % uuid.uuid4())
        crypto_util.encrypt(config.JOURNALIST_KEY, ll, ll_loc)
        flash("Thanks! We mapped your point.", "notification")

    if fh:
        try:
            # attempt to parse upload as GeoJSON FeatureCollection
            geojson_data = fh.file.read()
            geojson = json.loads( geojson_data )
            sort_id = len(features) + 1
            for feature in geojson["features"]:
                feature["properties"]["sort_id"] = sort_id
                sort_id = sort_id + 1

            # load existing GeoJSON
            features = [ ]
            if os.path.exists(g.sid + '.geojson'):
                currentfile = open(g.sid + '.geojson', 'r')
                existing = json.load(currentfile)
                currentfile.close()
                features = existing["features"]

            geojson["features"] = geojson["features"] + features

            # sanitize upload
            keys = geojson.keys()
            for key in keys:
                if key not in ["type", "features"]:
                    del geojson[key]
            
            gjfile = open(file_loc, 'w')
            gjfile.write( json.dumps( geojson ) )
            gjfile.close()
            flash("Thanks! We mapped data from '%s'."
                 % fh.filename or '[unnamed]', "notification")
        except:
            # non-GeoJSON file, or already encrypted
            flash("Thanks! We stored your document '%s' for review."
              % fh.filename or '[unnamed]', "notification")
        
        # whether it's GeoJSON or not, store encrypted version of upload for journalist
        file_loc = store.path(g.sid, "%s_doc.zip.gpg" % uuid.uuid4())

        s = StringIO()
        zip_file = zipfile.ZipFile(s, 'w')
        zip_file.writestr(fh.filename, fh.read())
        zip_file.close()
        s.reset()

        crypto_util.encrypt(config.JOURNALIST_KEY, s, file_loc)

    return redirect(url_for('lookup'))


@app.route('/delete', methods=('POST',))
@login_required
def delete():
    msgid = request.form['msgid']
    assert '/' not in msgid
    potential_files = os.listdir(g.loc)
    if msgid not in potential_files:
        abort(404)  # TODO are the checks necessary?
    crypto_util.secureunlink(store.path(g.sid, msgid))
    flash("Reply deleted.", "notification")

    return redirect(url_for('lookup'))


def valid_codename(codename):
    return os.path.exists(store.path(crypto_util.shash(codename)))


@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        codename = request.form['codename']
        if valid_codename(codename):
            session.update(codename=codename, logged_in=True)
            return redirect(url_for('lookup'))
        else:
            flash("Sorry, that is not a recognized codename.", "error")
    return render_template('login.html')


@app.route('/howto-disable-js')
def howto_disable_js():
    return render_template("howto-disable-js.html")


@app.route('/tor2web-warning')
def tor2web_warning():
    return render_template("tor2web-warning.html")


@app.route('/journalist-key')
def download_journalist_pubkey():
    journalist_pubkey = crypto_util.gpg.export_keys(config.JOURNALIST_KEY)
    return send_file(StringIO(journalist_pubkey),
                     mimetype="application/pgp-keys",
                     attachment_filename=config.JOURNALIST_KEY + ".asc",
                     as_attachment=True)


@app.route('/why-journalist-key')
def why_download_journalist_pubkey():
    return render_template("why-journalist-key.html")


@app.errorhandler(404)
def page_not_found(error):
    return render_template('notfound.html'), 404

if __name__ == "__main__":
    # TODO make sure debug is not on in production
    app.run(debug=True, port=8080)

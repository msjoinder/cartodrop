import mapnik, json
from base64 import b64encode

def prep_map(m):
  m.background = mapnik.Color('steelblue')
  s = mapnik.Style()
  r = mapnik.Rule()
  fill_symbolizer = mapnik.PolygonSymbolizer(mapnik.Color('#8c8'))
  r.symbols.append(fill_symbolizer)
  stroke_symbolizer = mapnik.LineSymbolizer(mapnik.Color('#000'), 0.25)
  r.symbols.append(stroke_symbolizer)
  s.rules.append(r)
  m.append_style('Default', s)
  
  shp = mapnik.Shapefile(file='../50m_cultural/ne_50m_admin_0_countries.shp')
  layer = mapnik.Layer('countries')
  layer.datasource = shp
  layer.styles.append('Default')
  m.layers.append(layer)
  return m

def get_coord_bounds(coord, bounds=[180, 90, -180, -90]):
  if(type( coord[0] ) == type( 10.0 ) or type( coord[0] ) == type( 10 )):
    # coord level
    bounds[0] = min(bounds[0], coord[0])
    bounds[1] = min(bounds[1], coord[1])
    bounds[2] = max(bounds[2], coord[0])
    bounds[3] = max(bounds[3], coord[1])
    return bounds
  else:
    # recursive into points
    for subset in coord:
      bounds = get_coord_bounds(subset, bounds)
    return bounds

def get_my_geojson(sid):
  # prep map label list
  items = [ ]

  # load map bounds
  currentfile = open(sid + '.geojson', 'r')
  geojson = json.load(currentfile)
  currentfile.close()
  for existing in geojson["features"]:
    bounds = get_coord_bounds(existing["geometry"]["coordinates"])
    minlng = bounds[0]
    minlat = bounds[1]
    maxlng = bounds[2]
    maxlat = bounds[3]
    if existing["properties"].has_key("msg"):
      items.append([existing["properties"]["sort_id"], existing["properties"]["msg"] ])

  # prep Mapnik
  m = mapnik.Map(400, 400)
  prep_map(m)
        
  # style GeoJSON
  s = mapnik.Style()
  r = mapnik.Rule()
  #pt_symbolizer = mapnik.PointSymbolizer()
  
  pt_symbolizer = mapnik.ShieldSymbolizer(mapnik.Expression('[sort_id]'),'DejaVu Sans Bold',8,mapnik.Color('#FFFFFF'),mapnik.PathExpression('static/i/mark.png'))
  pt_symbolizer.min_distance = 5
  pt_symbolizer.label_spacing = 10
  pt_symbolizer.displacement = (0,0)
  
  r.symbols.append(pt_symbolizer)
  s.rules.append(r)
  m.append_style('PointStyle', s)

  s = mapnik.Style()
  r = mapnik.Rule()
  fill_symbolizer = mapnik.PolygonSymbolizer(mapnik.Color('#a88'))
  r.symbols.append(fill_symbolizer)
  stroke_symbolizer = mapnik.LineSymbolizer(mapnik.Color('#000'), 0.1)
  r.symbols.append(stroke_symbolizer)
  s.rules.append(r)
  m.append_style('PolyStyle', s)
        
  # load GeoJSON file as layer
  pt = mapnik.GeoJSON(file=(sid + '.geojson'))
  pt_layer = mapnik.Layer('points')
  pt_layer.datasource = pt
  pt_layer.styles.append('PointStyle')
  pt_layer.styles.append('PolyStyle')
  m.layers.append(pt_layer)
        
  # center and output map of GeoJSON
  if minlat == maxlat:
    minlat = minlat - 10.0
    maxlat = maxlat + 10.0
  else:
    minlat = minlat - (maxlat-minlat) * 0.05
    maxlat = maxlat + (maxlat-minlat) * 0.05
  if minlng == maxlng:
    minlng = minlng - 10.0
    maxlng = maxlng + 10.0
  else:
    minlng = minlng - (maxlng-minlng) * 0.05
    maxlng = maxlng + (maxlng-minlng) * 0.05
  extent = mapnik.Box2d( minlng, minlat, maxlng, maxlat )
  m.zoom_to_box(extent)
  #m.zoom_all()

  worldimg = mapnik.Image(m.width, m.height)
  mapnik.render(m, worldimg)
  worlddata = worldimg.tostring("png")
  outimg = "data:image/png;base64," + b64encode(worlddata)
  return { "img": outimg, "labels": items }
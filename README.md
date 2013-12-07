![CartoDrop](/docs/images/logo.png)

CartoDrop is an open-source whistleblower submission system based on [SecureDrop](https://github.com/freedomofpress/securedrop).

## How to Install CartoDrop

[Install Mapnik](https://github.com/mapnik/mapnik/wiki/Mapnik-Installation) and check that it's working by creating a map with their [Getting Started guide](https://github.com/mapnik/mapnik/wiki/GettingStartedInPython).

Download content from [Natural Earth](http://www.naturalearthdata.com/).

Follow the same instructions as used on [SecureDrop](https://github.com/freedomofpress/securedrop).

![screenshot](/docs/images/screenshot.png)

## Changes to data security

A notice on the source's page explains levels of security.

Points and GeoJSON files submitted by sources are stored by source id and are not encrypted.

If they were encrypted by the journalist, then the program would be unable to generate a map.

If they were encrypted by the source, then every source would need their own key, allowing an
attacker to reduce security by creating bogus sources.

Points, GeoJSON files, and all other messages and uploads have encrypted copies in the same
directory used by SecureDrop. The journalist will download and decrypt the encrypted files
and messages as they would in SecureDrop.

## License

SecureDrop and CartoDrop are open source and released under the [GNU General Public License v2](/LICENSE). 

The [wordlist](/securedrop/wordlist) we use to generate source passphrases comes from [Diceware](http://world.std.com/~reinhold/diceware.html), and is licensed under Creative Commons Attribution 3.0 Unported thanks to A G Reinhold.

# Ian's Kodi Second Screen Repository

This Kodi repository distributes the two Kodi add-ons used by the second-screen
stack:

- `plugin.video.themoviedb.helper`
- `plugin.video.watchservice`

## Install

Install the repository zip in Kodi:

```text
https://raw.githubusercontent.com/iperez319/repository.secondscreen/main/zips/repository.secondscreen/repository.secondscreen-1.0.0.zip
```

Then use Kodi's `Install from repository` flow to install or update the two
add-ons.

## Build

Run the generator from this directory:

```sh
python3 create_repository.py
```

The generator packages the source add-ons from:

- `/Users/iperez/Documents/Projects/kodi/plugin.video.themoviedb.helper`
- `/Users/iperez/Documents/Projects/kodi/plugin.video.watchservice`

Both source repositories must be clean. The generated `zips/` tree is intended
to be committed and published as static files.

# Play Store listing assets

Graphics for the Google Play store listing. Not part of the app bundle.

| Asset | File | Play spec |
|---|---|---|
| Feature graphic | `feature-graphic.png` | 1024×500, PNG/JPEG, no transparency, ≤15 MB |
| App icon | `../../../public/icons/icon-512.png` (or `icon-512-maskable.png`) | 512×512, 32-bit PNG, ≤1 MB |
| Phone screenshots | not stored here — capture from the release build on a device/emulator | ≥2, 16:9 or 9:16, 320–3840 px |

## Feature graphic

`feature-graphic.svg` is the source; `feature-graphic.png` is the upload
artifact. Brand mark + `good`gorithm wordmark + tagline on the warm-black
`#121815`, colours and geometry from `web/src/theme.css` and CLAUDE.md's
visual-identity section. Manrope is embedded in the SVG as a base64 woff2,
so it rasterizes identically anywhere with no font install.

Regenerate the PNG after editing the SVG (from `web/`):

```sh
node -e "require('sharp')('android/store/feature-graphic.svg',{density:384}).resize(1024,500).flatten({background:'#121815'}).png().toFile('android/store/feature-graphic.png')"
```

(`sharp` comes in via `@capacitor/assets`.)

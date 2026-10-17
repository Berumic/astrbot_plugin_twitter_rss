# Card fallback fonts

These WOFF2 subsets come from the Noto project under the SIL Open Font License (see OFL.txt).

- NotoSans-Regular.woff2: Latin, IPA and combining marks (U+0020–036F).
- NotoSansMath-Regular.woff2: mathematical letters and symbols (U+2000–2BFF, U+1D400–1D7FF).

Sources:
https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSans
https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSansMath

Subsets were generated with fontTools. They are embedded as data URLs during rendering; no system font installation or fontTools runtime dependency is required. Include this fonts directory when packaging the plugin.

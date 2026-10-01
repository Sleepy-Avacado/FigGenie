# Fonts shipped with figgenie-paper-diagram

All files here are free fonts that may be embedded in SVG output and redistributed with the skill.
They are metric-compatible or visually close substitutes for the fonts most used in the corpus
(Arial 27%, Calibri 15%, Helvetica family 15%, Times family 11%, Computer Modern in TikZ figures).

| family | files | substitutes | license |
|---|---|---|---|
| Arimo | Arimo-*.ttf | Arial, Liberation Sans | SIL Open Font License 1.1 (Google / Monotype, ChromeOS core fonts) |
| Tinos | Tinos-*.ttf | Times New Roman, Liberation Serif | SIL Open Font License 1.1 |
| Carlito | Carlito-*.ttf | Calibri | SIL Open Font License 1.1 (tyPoland Lukasz Dziedzic) |
| TeX Gyre Heros | texgyreheros-*.otf | Helvetica, Helvetica Neue, Nimbus Sans | GUST Font License (LPPL-compatible) |
| TeX Gyre Termes | texgyretermes-*.otf | Times, Nimbus Roman | GUST Font License |
| Latin Modern Roman / Sans | lmroman10-*.otf, lmsans10-*.otf | Computer Modern | GUST Font License |
| DejaVu Sans | DejaVuSans*.ttf | Verdana, matplotlib default | Bitstream Vera / DejaVu license |
| Inter | Inter-*.otf | modern UI sans | SIL Open Font License 1.1 |
| Roboto | Roboto-*.otf | Roboto | Apache License 2.0 |
| Source Sans Pro | SourceSansPro-*.otf | Source Sans | SIL Open Font License 1.1 |

Sources: the files were copied from a TeX Live 2025 installation (`texmf-dist/fonts/{truetype,opentype}`),
which redistributes them under the licenses above. Full license texts are available in TeX Live
(`texmf-dist/doc/fonts/<name>/`) and from the upstream projects.

`fonts.json` maps figure-spec font keys and the family names found in papers to these files;
`scripts/embed_fonts.py` embeds them (subsetted when `fonttools` is installed) as `@font-face` data URIs.

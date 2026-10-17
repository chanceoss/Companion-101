Offline UI fonts

Fredoka and Nunito are distributed under their included SIL Open Font Licenses.

Authoritative sources:
https://github.com/google/fonts/tree/main/ofl/fredoka
https://github.com/google/fonts/tree/main/ofl/nunito

These bundled static instances were generated from the upstream variable TTFs
with fontTools 4.61.1 (instantiateVariableFont, updateFontNames=True):
  Fredoka.ttf: wght=600, wdth=100
  Nunito.ttf: wght=400
  Nunito-Bold.ttf: wght=700

Static instances give consistent text weight in Qt on Windows and Linux.
The application loads the local files; font downloads and fontTools are not
needed at runtime. Keep the OFL notices when redistributing these files.

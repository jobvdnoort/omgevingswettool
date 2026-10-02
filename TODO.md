# TODO

- Documentcontouren uit de Ontsluiten-response normaliseren zodra de productie-response een bruikbare officiële contour bevat; het MVP bewaart documentmetadata en inhoudelijke OW-geometrieën.
- IMRO-detailgeometrieën zijn niet geïmplementeerd. De officiële Geometrie Opvragen v1 API levert OW-geometrieën; er is geen Ruimtelijke Plannen-endpoint verzonnen. IMRO-documenten kunnen wel in de zoekresultaten staan.
- Presenteren v8 levert veel objectrelaties; het MVP vindt defensief expliciete `geometrieIdentificatie`-velden maar normaliseert nog niet elk objecttype/alle juridische relaties.
- File Geodatabase-export is niet aangeboden: runtime-detectie van schrijfbare FileGDB-drivers moet nog worden toegevoegd. GeoPackage kan in ArcGIS Pro worden geopend en geconverteerd.
- API-response-schema's kunnen evolueren; productiegebruik vereist aanvullende integratietests met een actuele sleutel.

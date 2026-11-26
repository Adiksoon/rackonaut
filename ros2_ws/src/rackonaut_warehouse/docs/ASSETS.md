# Asset provenance

The showcase uses [Steel Warehouse v2, LOD1 by tevy](https://tevy.dev/models/warehouse). The [pinned GLB](https://tevy.dev/models/warehouse/v2/lod1.glb) declares CC0 1.0 in its embedded asset metadata. Its SHA-256 was `989912e784a1fc1a822df7ddc4e3b65be53149744cc40a6d66a7e548d9760fc4`. See [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

The runtime Collada file is an adaptation of that geometry. glTF Transform 4.5.1 decoded Meshopt and dequantized the geometry. Compressed KTX2 textures and extension-specific materials were replaced with a matte palette. Blender 3.0.1 imported the resulting GLB and exported a triangulated Z-up Collada mesh in metres. The loading bay positions and the hall's steel frame, walls, roof, lighting fixtures and floor markings remain authored by tevy. The committed Collada file is the runtime input.

Rackonaut authored the racks, pallets, stock, safety markings, capture layout and inspection placards for this repository. Placards use standard ArUco `DICT_4X4_50` markers generated via Ubuntu OpenCV. The procedural hall option uses Rackonaut geometry.

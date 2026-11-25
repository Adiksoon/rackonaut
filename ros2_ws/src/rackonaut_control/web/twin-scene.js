import * as T from "three";

export const at = ([x, y, z = 0]) => new T.Vector3(x, z, -y);
export const accessColors = {
  OPEN: 0x38d7a1, PREPARING: 0xffc34f, RESERVED: 0xf36b75, INTRUSION: 0xff4560, FAULT: 0xe59afe,
};
export const slotColors = {
  uninspected: 0x698397, outside: 0x718395, planned: 0x60e4cb, inspecting: 0xe8fcff,
  observed: 0x66bafa, pending: 0x8bbaff, match: 0x64e0aa, discrepancy: 0xff7180,
  manual: 0xffbe6b, missed: 0xd8a4fa,
};
const box = new T.BoxGeometry();
const invisible = new T.MeshBasicMaterial({ visible: false });
const palette = {
  post: 0x2970b4, deck: 0xbc5929, beam: 0xfa853b, label_mount: 0x255789, guard: 0xedb845,
};

function solid(color) { return new T.MeshLambertMaterial({ color }); }
function block(parent, size, position, material) {
  const mesh = new T.Mesh(box, material);
  mesh.position.copy(position);
  mesh.scale.set(...size);
  parent.add(mesh);
  return mesh;
}
function boxes(parent, parts, category) {
  if (!parts.length) return;
  const mesh = new T.InstancedMesh(box, solid(0xffffff), parts.length);
  const transform = new T.Matrix4();
  const color = new T.Color();
  parts.forEach(([x, y, z, width, depth, height, r, g, b], i) => {
    transform.makeScale(width, height, depth);
    transform.setPosition(at([x, y, z]));
    mesh.setMatrixAt(i, transform);
    if (palette[category]) color.setHex(palette[category]);
    else if (category === "marking" && height < .012 && width > 35) color.setHex(0x263b50);
    else color.setRGB(r, g, b, T.SRGBColorSpace);
    mesh.setColorAt(i, color);
  });
  parent.add(mesh);
}

export function footprint(bounds, color, alpha, elevation, dashed = false) {
  const [x1, y1, x2, y2] = bounds;
  const area = new T.Mesh(new T.PlaneGeometry(x2 - x1, y2 - y1),
    new T.MeshBasicMaterial({ color, opacity: alpha, transparent: true, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  area.rotation.x = -Math.PI / 2;
  area.position.copy(at([(x1 + x2) / 2, (y1 + y2) / 2, elevation]));
  const vertices = [[x1, y1], [x1, y2], [x2, y2], [x2, y1], [x1, y1]].map(([x, y]) => at([x, y, elevation + .004]));
  const stroke = dashed ? new T.LineDashedMaterial({ color, dashSize: .35, gapSize: .18 }) : new T.LineBasicMaterial({ color });
  const border = new T.Line(new T.BufferGeometry().setFromPoints(vertices), stroke);
  border.computeLineDistances();
  const group = new T.Group();
  group.add(area, border);
  return { group, area, border };
}
export function tint(area, color, opacity) {
  area.area.material.color.setHex(color);
  area.area.material.opacity = opacity;
  area.border.material.color.setHex(color);
}

function signalView(scene, signal, parts) {
  const origin = at(signal.position);
  const base = solid(0x213043);
  const pole = solid(0x73879a);
  const lenses = [];
  for (const [name, z, width, depth, height] of parts) {
    const lens = ["red", "yellow", "green"].includes(name);
    const material = lens ? new T.MeshBasicMaterial({ color: 0x253040 }) : name === "pole" ? pole : base;
    const mesh = block(scene, [width, height, depth], origin.clone().add(new T.Vector3(0, z, 0)), material);
    if (lens) lenses.push(mesh);
  }
  return { ...signal, lenses };
}

export function makeWarehouse(layout, scene) {
  const { floor, pad, crossing_x: crossing, scene: source } = layout;
  const farWall = solid(0x263b4d);
  const trim = solid(0x3b5870);
  const building = new T.Group();
  scene.add(building);
  // The cutaway keeps the physical wall footprint and a low perimeter sill.
  for (const [x, y, , width, depth, height] of source.shell) {
    block(building, [width, height * .075, depth], at([x, y, height * .0375]), farWall);
    block(building, [width + .04, .055, depth + .04], at([x, y, height * .075]), trim);
  }
  for (const [category, parts] of Object.entries(source.parts)) boxes(building, parts, category);
  const grid = new T.GridHelper(floor.width, 40, 0x3c566d, 0x334a60);
  grid.scale.z = floor.height / floor.width;
  grid.position.copy(at([floor.x + floor.width / 2, floor.y + floor.height / 2, .017]));
  grid.material.transparent = true;
  grid.material.opacity = .49;
  scene.add(grid);
  const padBox = [pad.x - pad.width / 2, pad.y - pad.height / 2, pad.x + pad.width / 2, pad.y + pad.height / 2];
  scene.add(footprint(padBox, 0x6eead4, .31, .033).group);

  const points = [at([crossing, layout.aisles[0].y, .055]), at([crossing, layout.aisles.at(-1).y, .055])];
  const corridor = new T.Line(new T.BufferGeometry().setFromPoints(points),
    new T.LineDashedMaterial({ color: 0xa5bed6, opacity: .78, transparent: true, dashSize: .33, gapSize: .26 }));
  corridor.computeLineDistances();
  scene.add(corridor);

  const zones = Object.fromEntries(Object.entries(layout.safety_fields || {}).map(([id, bounds]) => {
    const shape = footprint(bounds, accessColors.FAULT, .15, .023);
    scene.add(shape.group);
    return [id, shape];
  }));
  const lasers = Object.fromEntries(Object.entries(layout.laser_fields || {}).map(([id, scanner]) => {
    scene.add(footprint(scanner.field, 0x63cbff, .055, .040, true).group);
    const mesh = new T.Mesh(new T.CylinderGeometry(.14, .17, .15, 12), solid(0x53cdeb));
    mesh.position.copy(at(scanner.pose));
    scene.add(mesh);
    return [id, scanner];
  }));
  const signals = layout.safety_fields ? source.signals.map(signal => signalView(scene, signal, source.signal_parts)) : [];

  const picks = [];
  const slots = {};
  const bayRim = new T.EdgesGeometry(box);
  const highlightTracked = new T.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: .18, depthWrite: false });
  const unverified = new T.MeshBasicMaterial({ color: 0x7aa0b9, transparent: true, opacity: .14, depthWrite: false });
  const crate = solid(0xb9854e);
  const skid = solid(0x754a2e);
  for (const [id, slot] of Object.entries(layout.slots)) {
    const [x, row, deck] = slot.bay_center;
    const [, face] = slot.label;
    const position = at([x, face - .04, deck + .44]);
    const size = [slot.bay_width - .15, .86, .12];
    const pick = block(scene, size, position, invisible);
    pick.userData.selection = { type: "slot", id };
    picks.push(pick);
    const outline = new T.LineSegments(bayRim, new T.LineBasicMaterial({ color: slotColors.uninspected }));
    outline.position.copy(position);
    outline.scale.set(...size);
    scene.add(outline);
    const faceMesh = block(scene, [size[0], .055, .12], at([x, face - .065, deck + .05]), highlightTracked.clone());
    const cover = block(scene, [size[0], size[1], .02], position, unverified);
    const cargo = new T.Group();
    block(cargo, [1.05, .13, .79], at([x, row, deck + .075]), skid);
    block(cargo, [.84, .67, .66], at([x, row, deck + .47]), crate);
    cargo.visible = false;
    scene.add(cargo);
    slots[id] = { outline, face: faceMesh, cover, cargo };
  }

  const rack = layout.racks[0];
  const aisleWidth = (layout.racks[1].y - rack.y) - rack.height;
  const aisles = {};
  for (const aisle of layout.aisles) {
    if (!aisle.functional) continue;
    const bound = [rack.x, aisle.y - aisleWidth / 2, rack.x + rack.width, aisle.y + aisleWidth / 2];
    const outline = footprint(bound, 0x8ee9dc, .045, .030);
    outline.group.visible = false;
    scene.add(outline.group);
    aisles[aisle.id] = outline;
    const target = block(scene, [rack.width, .03, aisleWidth], at([rack.x + rack.width / 2, aisle.y, .047]), invisible);
    target.userData.selection = { type: "aisle", id: aisle.id };
    picks.push(target);
  }
  return { zones, lasers, signals, slots, aisles, picks };
}

export function makeAircraft(scene) {
  const drone = new T.Group();
  scene.add(drone);
  const body = solid(0x9afcdb);
  const edge = new T.MeshBasicMaterial({ color: 0xccfff3 });
  const dark = solid(0x254158);
  // Slightly enlarged glyph for readability at warehouse scale. Its origin is the ROS base.
  block(drone, [.61, .21, .43], new T.Vector3(), body);
  block(drone, [.18, .11, .27], new T.Vector3(.31, .03, 0), edge);
  const locator = new T.Mesh(new T.TorusGeometry(.66, .029, 8, 36), edge);
  locator.rotation.x = Math.PI / 2;
  drone.add(locator);
  for (const [x, z] of [[-.38, -.38], [.38, -.38], [-.38, .38], [.38, .38]]) {
    const arm = block(drone, [.55, .07, .085], new T.Vector3(x / 2, 0, z / 2), dark);
    arm.rotation.y = -Math.atan2(z, x);
    const rim = new T.Mesh(new T.TorusGeometry(.175, .021, 8, 20), edge);
    rim.rotation.x = Math.PI / 2;
    rim.position.set(x, .08, z);
    drone.add(rim);
    block(drone, [.28, .028, .055], new T.Vector3(x, .076, z), body);
  }
  drone.visible = false;
  return { drone, body, edge };
}

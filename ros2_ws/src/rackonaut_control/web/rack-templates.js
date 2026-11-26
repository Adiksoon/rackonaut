import * as THREE from "three";

export const world = ([x, y, z]) => new THREE.Vector3(x, z, -y);

export function instances(boxes, color, metalness = .12) {
  if (!boxes.length) return null;
  const mesh = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({color, metalness, roughness: .72}),
    boxes.length,
  );
  const item = new THREE.Object3D();
  boxes.forEach(([x, y, z, width, height, depth], i) => {
    item.position.set(x, y, z);
    item.scale.set(width, height, depth);
    item.updateMatrix();
    mesh.setMatrixAt(i, item.matrix);
  });
  mesh.computeBoundingBox();
  return mesh;
}

function addInstances(group, boxes, color, metalness) {
  const mesh = instances(boxes, color, metalness);
  if (mesh) group.add(mesh);
}

export function rackTemplate(row) {
  const group = new THREE.Group();
  group.name = row.id;
  group.rotation.y = row.yaw_rad;
  const [[start, front], [end, rear]] = row.bounds_uv;
  const [base, top] = row.vertical_extent_m;
  const [length, depth, height] = row.dimensions_m;
  // Visual profiles scale with the measured envelope. These are the generic
  // construction sections of the template, not measurements of steel gauge.
  const steel = Math.min(depth * .083, height * .033);
  const decking = depth * .046;
  const beam = steel * 1.24;
  const stations = row.stations_u.map(u => THREE.MathUtils.clamp(u, start + steel/2, end - steel/2));
  const faces = [front + steel/2, rear - steel/2];
  const posts = stations.flatMap(u => faces.map(v => [u, (base + top)/2, -v, steel, height, steel]));
  const shoes = stations.flatMap(u => faces.map(v => [u, base + steel*.12, -v, steel*1.7, steel*.24, steel*1.7]));
  const crossbars = stations.flatMap(u => [base + height*.19, top - steel*.95].map(z =>
    [u, z, -(front + rear)/2, steel*.56, beam*.53, depth - steel]));
  const beams = [];
  row.levels_m.forEach((z, index) => {
    // At each level, adjacent stations delimit repeated complete bays.
    const decks = [];
    for (let i = 1; i < stations.length; i++) {
      const low = stations[i-1], high = stations[i], span = high - low;
      decks.push([(low + high)/2, z - decking/2, -(rear + front)/2, span - steel, decking, depth - steel*.95]);
      for (const face of faces) {
        beams.push([(low + high)/2, z - decking - beam/2, -face, span - steel*.52, beam, steel*.79]);
      }
    }
    addInstances(group, decks, ["#d4dfed", "#c0d0e2", "#e0e7f1"][index % 3], .06);
  });
  addInstances(group, [...posts, ...crossbars], "#405a76");
  addInstances(group, shoes, "#516375");
  addInstances(group, beams, "#ba733b", .02);
  return group;
}

function rect(bounds, height) {
  const [[u0, v0], [u1, v1]] = bounds;
  return [(u0 + u1)/2, height, -(v0 + v1)/2, u1 - u0, v1 - v0];
}

function surface(bounds, height, color, alpha = 1) {
  const [x, y, z, width, depth] = rect(bounds, height);
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, depth),
    new THREE.MeshBasicMaterial({color, opacity: alpha, transparent: alpha !== 1, depthWrite: alpha === 1}));
  mesh.rotation.x = -Math.PI/2;
  mesh.position.set(x, y, z);
  return mesh;
}

function layoutGrid(bounds, height) {
  const [[a, b], [c, d]] = bounds;
  const step = Math.max(1, Math.ceil(Math.max(c-a, d-b)/36));
  const points = [];
  for (let x = Math.ceil(a/step)*step; x < c; x += step) points.push([x,height,-b], [x,height,-d]);
  for (let z = Math.ceil(b/step)*step; z < d; z += step) points.push([a,height,-z], [c,height,-z]);
  return new THREE.LineSegments(new THREE.BufferGeometry().setAttribute(
    "position", new THREE.Float32BufferAttribute(points.flat(), 3)), new THREE.LineBasicMaterial({color: "#cad6e2"}));
}

export function warehouseTemplate(twin) {
  const model = new THREE.Group();
  for (const row of twin.rows) model.add(rackTemplate(row));
  const context = new THREE.Group();

  if (twin.floor) {
    const floor = new THREE.Group();
    floor.rotation.y = twin.floor.yaw_rad;
    const bounds = twin.floor.bounds_uv.map(point => [...point]);
    const angle = twin.floor.yaw_rad;
    const include = ([x,y]) => {
      const local = [x*Math.cos(angle)+y*Math.sin(angle), -x*Math.sin(angle)+y*Math.cos(angle)];
      local.forEach((coordinate, axis) => {
        bounds[0][axis] = Math.min(bounds[0][axis], coordinate-.45);
        bounds[1][axis] = Math.max(bounds[1][axis], coordinate+.45);
      });
    };
    for (const row of twin.rows) {
      const [[u0,v0],[u1,v1]] = row.bounds_uv;
      for (const u of [u0,u1]) for (const v of [v0,v1]) {
        include([u*Math.cos(row.yaw_rad)-v*Math.sin(row.yaw_rad), u*Math.sin(row.yaw_rad)+v*Math.cos(row.yaw_rad)]);
      }
    }
    for (const wall of twin.walls) wall.endpoints_xy.forEach(include);
    if (twin.dock) include(twin.dock.position_m);
    const [x,y,z,width,depth] = rect(bounds, twin.floor.z_m);
    addInstances(floor, [[x,y-.092,z,width,.17,depth]], "#c2cdd9", 0);
    floor.add(surface(bounds, y-.005, "#e5ecf3"), layoutGrid(bounds, y+.003));
    context.add(floor);
    for (const row of twin.rows) {
      const shade = new THREE.Group();
      shade.rotation.y = row.yaw_rad;
      shade.add(surface(row.bounds_uv, y+.011, "#627a95", .19));
      context.add(shade);
    }
  }

  for (const aisle of twin.aisles) {
    const group = new THREE.Group();
    const [[u0, v0], [u1, v1]] = aisle.bounds_uv;
    const z = aisle.z_m + .016;
    const stripe = (u1 - u0) / 85;
    group.rotation.y = aisle.yaw_rad;
    group.add(surface([[u0, v0+.17], [u1, v1-.17]], z, "#cbdcec", .65));
    for (const v of [v0+.22, v1-.22]) group.add(surface([[u0, v], [u1, v+stripe/3]], z+.005, "#8fa9c6", .58));
    context.add(group);
  }

  for (const wall of twin.walls) {
    const [a, b] = wall.endpoints_xy;
    const run = Math.hypot(b[0]-a[0], b[1]-a[1]);
    const group = new THREE.Group(), height = wall.display_height_m;
    group.position.copy(world([(a[0]+b[0])/2, (a[1]+b[1])/2, wall.z_m]));
    group.rotation.y = Math.atan2(b[1]-a[1], b[0]-a[0]);
    addInstances(group, [[0,height/2,0,run,height,.13], [0,height+.025,0,run,.05,.20]], "#9bacc0", .07);
    context.add(group);
  }

  if (twin.dock) {
    const pad = new THREE.Group(), ground = twin.floor?.z_m ?? twin.dock.position_m[2];
    pad.position.copy(world([...twin.dock.position_m.slice(0,2), ground]));
    pad.rotation.y = twin.dock.yaw_rad ?? 0;
    addInstances(pad, [[0,.065,0,1.48,.13,1.23]], "#456581");
    addInstances(pad, [[0,.143,0,1.29,.027,1.04]], "#a8c8e2");
    const rim = [[-.58,.161,0,.03,.007,.86], [.58,.161,0,.03,.007,.86],
      [0,.161,-.43,1.17,.007,.03], [0,.161,.43,1.17,.007,.03]];
    addInstances(pad, [...rim, [-.10,.166,0,.043,.008,.34], [.10,.166,0,.043,.008,.34],
      [0,.166,0,.21,.008,.043]], "#edf6ff");
    context.add(pad);
  }

  const route = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(
    twin.route_edges_m.flatMap(edge => edge.map(world))),
  new THREE.LineDashedMaterial({color: "#2475c9", dashSize: .30, gapSize: .13, transparent: true, opacity: .9}));
  route.computeLineDistances();
  return {model, context, route};
}

export function measuredCloud(packet) {
  const raw = Uint8Array.from(atob(packet.points_f32le), char => char.charCodeAt(0));
  if (raw.byteLength !== packet.point_count*12) throw new Error("The measured cloud is incomplete.");
  const source = new DataView(raw.buffer);
  const xyz = new Float32Array(packet.point_count*3);
  const colors = new Float32Array(xyz.length);
  const low = new THREE.Color("#3ab8ac"), middle = new THREE.Color("#548cdc"), high = new THREE.Color("#df9b62");
  const tint = new THREE.Color();
  for (let i = 0; i < xyz.length; i += 3) {
    const x = source.getFloat32(i*4, true), y = source.getFloat32((i+1)*4, true), z = source.getFloat32((i+2)*4, true);
    if (![x,y,z].every(Number.isFinite)) throw new Error("Invalid coordinates in the measured cloud.");
    xyz.set([x,z,-y], i);
    const height = THREE.MathUtils.clamp(z / 10, 0, 1);
    if (height < .5) tint.copy(low).lerp(middle, height*2);
    else tint.copy(middle).lerp(high, height*2-1);
    tint.toArray(colors, i);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(xyz,3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors,3));
  geometry.computeBoundingBox();
  return new THREE.Points(geometry, new THREE.PointsMaterial({
    vertexColors: true, size: .067, transparent: true, depthWrite: false,
  }));
}

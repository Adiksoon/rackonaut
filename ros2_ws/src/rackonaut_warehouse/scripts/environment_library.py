"""Build a warehouse library from declarative geometry and inventory fixtures."""

from dataclasses import dataclass
import json
from math import floor, pi
from pathlib import Path
from random import Random
from xml.etree import ElementTree as ET

from generate import (CARTONS, SIGNAL_STACK, add, box, cargo, charging_station, light, link,
                      localization_infrastructure, material, numbers, plane_label, twin_geometry, world_base)


PROFILES = ('distribution-center', 'high-bay', 'logistics-hub')
FUNCTIONAL = ('A', 'B')
WHITE = (.88, .92, .92)
YELLOW = (.94, .71, .13)
STEEL = (.17, .24, .28)
CHARCOAL = (.10, .14, .16)
DECK = (.42, .48, .48)
PORTAL_WIDTH = 1.72
HALF_ENVELOPE = .33
BODY_RADIUS = .48
BODY_HALF_HEIGHT = .17


@dataclass(frozen=True)
class Bank:
    name: str
    axis: str
    start: float
    bay_pitch: float
    bays: int
    rows: list[float]
    aisles: list[str]

    @property
    def end(self):
        return self.start + self.bays * self.bay_pitch

    def point(self, along, lateral, z):
        return (along, lateral, z) if self.axis == 'x' else (lateral, along, z)

    def add(self, parent, name, at, size, color=None, collision=False):
        box(parent, name, self.point(*at), self.point(*size), color, collision)

    def center(self, index):
        return (self.rows[index] + self.rows[index + 1]) / 2


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def texture_label(parent, variant, name, point, size, yaw=0.):
    plane_label(parent, name, point, *size, yaw=yaw)
    uri = parent[-1].find('material/pbr/metal/albedo_map')
    uri.text = f'model://rackonaut_warehouse_library/{variant}/{name}.png'


def textures_for(path, spec, aisles, inventory):
    import cv2
    import numpy as np

    path.mkdir(parents=True, exist_ok=True)
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    marker_image = getattr(aruco, 'generateImageMarker', None) or aruco.drawMarker
    font = cv2.FONT_HERSHEY_DUPLEX
    color = tuple(int(component * 255) for component in reversed(spec['design']['frame']))

    def save(name, image):
        if not cv2.imwrite(str(path / f'{name}.png'), image):
            raise RuntimeError(f'Could not save {name}.png')

    def text(image, value, xy, scale, ink=color, weight=3):
        cv2.putText(image, value, xy, font, scale, ink, weight, cv2.LINE_AA)

    def card(name, caption, value, identifier):
        image = np.full((288, 512, 3), 246, np.uint8)
        cv2.rectangle(image, (0, 0), (511, 287), color, 12)
        if identifier is None:
            cv2.rectangle(image, (40, 73), (192, 216), (116, 112, 102), -1)
            for x in range(38, 185, 20):
                cv2.line(image, (x, 216), (min(x + 60, 191), 74), (169, 159, 146), 7)
        else:
            marker = marker_image(dictionary, identifier, 216)
            image[36:252, 26:242] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        text(image, caption, (257, 98), .88)
        text(image, value, (250, 158), 1.08, (25, 32, 35), 2)
        text(image, 'RACKONAUT', (254, 220), .75)
        save(name, image)

    def sign(name, title, subtitle):
        image = np.empty((265, 1000, 3), np.uint8)
        image[:] = color
        cv2.rectangle(image, (7, 7), (992, 257), (226, 229, 220), 7)
        scale = min(2.75, 2.75 * 18 / len(title))
        text(image, title, (36, 125), scale, (244, 247, 245), 4)
        text(image, subtitle, (43, 204), 1.2, (224, 238, 216))
        save(name, image)

    sign('hall-id', spec['title'].upper(), 'RACKONAUT   /   WAREHOUSE OPERATIONS')
    sign('dock-id', 'RACKONAUT DOCK', 'TECHNICAL ZONE D   /   KEEP CLEAR')
    for name in aisles:
        sign(f'aisle-{name}', f'AISLE {name}', 'DRONE INSPECTION' if name in FUNCTIONAL else 'STAGING SCENERY')
    for area in spec['staging']:
        sign(area['name'], area['name'].replace('-', ' ').upper(), {
            'buffer': 'TEMPORARY STORAGE', 'dispatch': 'OUTBOUND LOGISTICS',
            'lifts': 'MATERIAL HANDLING', 'receiving': 'INBOUND LOGISTICS',
        }[area['usage']])
    for row in inventory:
        card('loc-' + row['slot_id'], 'LOCATION', row['slot_id'], row['marker'])
        if row['pallet']:
            card('hu-' + row['slot_id'], 'HANDLING UNIT', row['pallet'] if row['pallet_marker'] is not None else 'N/A',
                 row['pallet_marker'])


def shell(world, spec):
    bounds = spec['bounds']
    x0, x1 = bounds['x']
    y0, y1 = bounds['y']
    height = bounds['height']
    width, length = y1 - y0, x1 - x0
    middle, y = (x0 + x1) / 2, (y0 + y1) / 2
    design = spec['design']
    frame, wall = design['frame'], design['liner']
    area = link(world, 'warehouse_shell')
    box(area, 'floor', (middle, y, -.12), (length, width, .24), design['floor'], True)
    for side, side_y in enumerate((y0 - .10, y1 + .10)):
        box(area, f'side_{side}', (middle, side_y, height / 2), (length, .20, height), wall, True)
        box(area, f'kick_{side}', (middle, side_y + .11 * (1-2*side), .52), (length, .07, 1.04), frame)
    for end, end_x in enumerate((x0 - .10, x1 + .10)):
        box(area, f'end_{end}', (end_x, y, height / 2), (.20, width, height), wall, True)
        for index, door_y in enumerate((y0 + 4., y0 + 9., y1 - 7.)):
            inner_x = end_x + .14 * (1-2*end)
            box(area, f'door_{end}_{index}', (inner_x, door_y, 2.05), (.08, 2.85, 4.10), STEEL)
            box(area, f'door_tint_{end}_{index}', (inner_x + .05*(1-2*end), door_y, 2.50), (.035, 2.40, .40), design['accent'])
    box(area, 'roof', (middle, y, height + .10), (length, width, .20), frame, True)
    style = design['shell']
    pitch = {'distribution': 6.4, 'high-bay': 7.2, 'logistics': 8.5}[style]
    for index in range(floor((length-3.) / pitch) + 1):
        x = x0 + 1.5 + index * pitch
        box(area, f'rafter_{index}', (x, y, height - .18), (.24, width, .36), frame, True)
        for side, column_y in enumerate((y0 + .19, y1 - .19)):
            box(area, f'column_{index}_{side}', (x, column_y, height / 2), (.34, .38, height), frame, True)
        if style == 'high-bay':
            box(area, f'upper_truss_{index}', (x, y, height - .86), (.22, width, .16), STEEL, True)
        if style == 'distribution' and index % 2 == 0:
            box(area, f'roof_liner_{index}', (x+.5, y, height-.052), (.82, width-.26, .105), (.77,.86,.92))
        if style == 'logistics':
            box(area, f'west_to_east_{index}', (x, y, height-.58), (.15, width-.30, .14), design['accent'], True)
    for y_index, fixture_y in enumerate((y0+width*.23, y, y1-width*.23)):
        for x_index, fraction in enumerate((.17, .50, .83)):
            x = x0 + length * fraction
            key = f'{y_index}_{x_index}'
            z = height - 1.03
            box(area, f'led_housing_{key}', (x, fixture_y, z), (1.72, .30, .14), STEEL, True)
            box(area, f'led_strip_{key}', (x, fixture_y, z-.078), (1.58, .235, .029), WHITE)
            panel = area[-1].find('material')
            add(panel, 'emissive', '0.65 0.68 0.67 1')
            light(world, f'light_{key}', 'point', (x, fixture_y, z-.14), (.55,.57,.58))
    return area


def aisle_data(spec, banks):
    depth = spec['rack']['depth']
    values = {}
    for bank in banks:
        if bank.axis not in {'x','y'} or len(bank.aisles) != len(bank.rows)-1 or bank.bays < 1:
            raise ValueError(f'Invalid bank geometry in {bank.name}')
        for i, name in enumerate(bank.aisles):
            width = bank.rows[i+1] - bank.rows[i] - depth
            if name in values or width <= 2 * (HALF_ENVELOPE + BODY_RADIUS):
                raise ValueError(f'Invalid or repeated aisle {name}')
            values[name] = {'bank': bank, 'next_row': i+1, 'axis': bank.axis,
                            'center': bank.center(i), 'width': width, 'functional': name in FUNCTIONAL}
    if not set(FUNCTIONAL) <= values.keys() or any(values[key]['axis'] != 'x' for key in FUNCTIONAL):
        raise ValueError('The current two-aisle profile requires functional A and B along +X.')
    return values


def rack_rows(world, spec, banks, aisles):
    design, rack = spec['design'], spec['rack']
    depth, zenith = rack['depth'], rack['height']
    variant = spec['id']
    authored = {}
    markers, identifiers, ground_truth = set(), set(), []
    for item in spec['locations']:
        aisle, bay, level = item['aisle'], item['bay'], item['level']
        zone = aisles[aisle]
        bank = zone['bank']
        identifiers_here = [x for x in (item['marker'],item['pallet_marker']) if x is not None]
        slot = f'{aisle}-{bay:02}-{level:02}'
        if (not zone['functional'] or not 1 <= bay <= bank.bays or not 1 <= level <= len(rack['levels'])
                or slot in identifiers or len(set(identifiers_here)) != len(identifiers_here)
                or not all(0 <= x < 50 and x not in markers for x in identifiers_here)):
            raise ValueError(f'Invalid placement or ArUco id for {slot}')
        identifiers.add(slot)
        markers.update(identifiers_here)
        authored[(bank.name, zone['next_row'], bay, level)] = {**item, 'slot_id': slot}

    rng = Random(spec['seed'])
    for bank in banks:
        for row, y in enumerate(bank.rows):
            parent = link(world, f'rack_row_{bank.name}_{row+1}')
            face = y-depth/2
            for post in range(bank.bays+1):
                x = bank.start + post*bank.bay_pitch
                for side in (-1,1):
                    bank.add(parent,f'post_{post}_{side}',(x,y+side*(depth/2-.07),zenith/2),(.14,.14,zenith),design['frame'],True)
                bank.add(parent,f'guard_{post}',(x,face+.10,.30),(.22,.22,.60),YELLOW,True)
            for level, deck in enumerate(rack['levels'],1):
                middle = (bank.start+bank.end)/2
                bank.add(parent, f'deck_{level}',(middle,y,deck-.05),(bank.end-bank.start,depth,.10),DECK,True)
                for side in (-1, 1):
                    bank.add(parent,f'beam_{level}_{side}',(middle,y+side*(depth/2-.06),deck-.09),
                             (bank.end-bank.start,.12,.18),design['beam'])
                for bay in range(1,bank.bays+1):
                    tag = f'b{bay}_l{level}'
                    x = bank.start+(bay-.5)*bank.bay_pitch
                    item = authored.get((bank.name,row,bay,level))
                    if item:
                        label = x-.54, face-.008, deck+.31
                        box(parent, f'label_mount_{tag}', (x-.54,face+.037,deck+.31), (.63,.08,.37),design['frame'])
                        texture_label(parent,variant,'loc-'+item['slot_id'],label,(.62,.349))
                        if item['pallet']:
                            cargo(parent,f'inspection_{tag}',x+.38,face+.51,deck,rng,detailed=True,collision=True,
                                  quality_shape='torn' if item['scenario']=='damaged' else 'intact')
                            texture_label(parent,variant,'hu-'+item['slot_id'],
                                          (x+.38,face+.157,deck+.49),(.59,.332))
                        ground_truth.append({**item,'label':label,'bay_center':(x,y,deck),
                                             'bay_width':bank.bay_pitch,
                                             'viewpoint':(x-.04,aisles[item['aisle']]['center'],deck+.39,90)})
                        continue
                    for unit in (-1,1):
                        if rng.random() > rack['fill']:
                            continue
                        p, cy = x+unit*.58, y+rng.uniform(-.10,.10)
                        scale = rng.uniform(.48,.94)
                        bank.add(parent,f'decor_{tag}_{unit}_skid',(p,cy,deck+.068),(.97,.86,.12),(.47,.32,.20))
                        bank.add(parent,f'decor_{tag}_{unit}_load',(p,cy,deck+.13+scale/2),
                                 (rng.uniform(.68,.90),.72,scale),rng.choice(CARTONS),True)
    return sorted(ground_truth,key=lambda x:x['slot_id'])


class AerialRig:
    """The GOAL 27B clearance is carried over to horizontal tunnels and open portals."""

    def __init__(self, world, spec, aisles):
        self.link = link(world, 'protected_flight_infrastructure')
        self.z = spec['flight']['height']
        self.roof = spec['bounds']['height']
        self.frame = spec['design']['frame']
        self.accent = spec['design']['accent']
        self.parts, self.screens = [], []
        self.profile = self.network(spec, aisles)
        for start, end, kind in self.profile['edges']:
            if kind == 'tunnel':
                self.tunnel(self.profile['nodes'][start], self.profile['nodes'][end])
        self.shaft(*self.profile['nodes']['dock'][:2])
        for zone in FUNCTIONAL:
            self.portal(*self.profile['nodes'][f'entry_{zone}'][:2])
        self.profile.update(parts=self.parts, screens=self.screens)

    def part(self, point, size, color, screen=False):
        dest = self.screens if screen else self.parts
        name = f'{"screen" if screen else "frame"}_{len(dest)}'
        box(self.link, name, point, size, color, True)
        if screen:
            add(self.link[-2], 'transparency', '.76')
        dest.append([*point,*size,*color])

    def network(self, spec, aisles):
        flight = spec['flight']
        dx, dy = flight['dock']
        trunk = flight['trunk_x']
        if self.z-.65 <= spec['rack']['height'] or self.z+.68 >= self.roof-1.1:
            raise ValueError('Tunnel must fit between the racks and occupied roof space.')
        nodes = {'dock':[dx,dy,.05], 'shaft':[dx,dy,self.z], 'junction':[trunk,dy,self.z]}
        edges = [['dock','shaft','shaft'], ['shaft','junction','tunnel']]
        gates, volumes = {}, {}
        previous = 'junction'
        if dy <= max(aisles[zone]['center'] for zone in FUNCTIONAL):
            raise ValueError('The technical dock must be upstream of the trunk branches.')
        for zone in sorted(FUNCTIONAL,key=lambda name:-aisles[name]['center']):
            y = aisles[zone]['center']
            x = flight['portals'][zone]
            bank = aisles[zone]['bank']
            branch, entry, foot = (f'{name}_{zone}' for name in ('trunk','entry','foot'))
            nodes.update({branch:[trunk,y,self.z],entry:[x,y,self.z],foot:[x,y,.86]})
            edges += [[previous,branch,'tunnel'],[branch,entry,'tunnel'],[entry,foot,zone]]
            previous = branch
            gates[zone] = [x-.80,y-.80,x+.80,y+.80]
            volumes[zone] = [bank.start+.25,y-.66,.56,bank.end-.25,y+.66,spec['rack']['levels'][-1]+.75]
        technical = [dx-1.58,dy-1.40,dx+1.58,dy+1.40]
        return {'nodes':nodes,'edges':edges,'gates':gates,'inspection_volumes':volumes,'technical':technical,
                'pad':dict(x=dx,y=dy,z=.05,yaw_deg=0.,width=2.65,height=2.1)}

    def tunnel(self, start, end):
        x, y = [(a+b)/2 for a,b in zip(start[:2],end[:2])]
        along_x = start[1] == end[1]
        length = abs((end[0]-start[0]) if along_x else (end[1]-start[1]))-2.04
        if length <= .05:
            return

        def xy(along, across, z):
            return (x+along,y+across,z) if along_x else (x+across,y+along,z)

        def size(a,b,z):
            return (a,b,z) if along_x else (b,a,z)

        for side in (-1,1):
            self.part(xy(0,side*.91,self.z),size(length,.04,1.10),self.frame,screen=True)
            for level in (-.60,.59):
                self.part(xy(0,side*.91,self.z+level),size(length,.08,.08),self.frame)
        self.part(xy(0,0,self.z-.61),size(length,1.78,.028),self.frame,screen=True)
        for offset in (-length/2,length/2):
            self.part(xy(offset,0,self.z+.60),size(.08,1.92,.09),self.accent)
        count = max(1, int(length/4.))
        for i in range(count):
            offset = length*((i+.5)/count-.5)
            self.part(xy(offset,0,self.z+.64),size(.09,2.02,.09),self.frame)
            self.part(xy(offset,0,self.z-.62),size(.09,1.94,.08),self.frame)
            for side in (-1,1):
                bottom, top = self.z+.68, self.roof-.02
                self.part(xy(offset,side*.92,(bottom+top)/2),size(.055,.055,top-bottom),self.frame)

    def portal(self, x, y):
        offset = PORTAL_WIDTH/2+.055
        for side in (-1,1):
            for end in (-1,1):
                self.part((x+side*offset,y+end*offset,self.z),(.11,.11,1.25),self.accent)
            for level in (-.61,.60):
                self.part((x+side*offset,y,self.z+level),(.10,PORTAL_WIDTH,.085),self.frame)
                self.part((x,y+side*offset,self.z+level),(PORTAL_WIDTH,.10,.085),self.frame)
        self.part((x,y,self.z+.61),(PORTAL_WIDTH,PORTAL_WIDTH,.035),self.frame,screen=True)

    def shaft(self, x, y):
        for sx in (-1,1):
            for sy in (-1,1):
                self.part((x+sx*.96,y+sy*.96,(self.z-.70)/2),(.11,.11,self.z-.70),self.accent)
            self.part((x+sx*.96,y,(self.z-1.95)/2+1.25),(.045,1.77,self.z-3.0),self.frame,screen=True)
        for z in (2.4,self.z-1.2):
            for side in (-1,1):
                self.part((x,y+side*.96,z),(1.94,.06,.09),self.frame)
                self.part((x+side*.96,y,z),(.06,1.94,.09),self.frame)
        self.portal(x,y)


def ground(world, spec, aisles, profile):
    variant = spec['id']
    frame, accent = (spec['design'][key] for key in ('frame','accent'))
    x0, x1 = spec['bounds']['x']
    y0, y1 = spec['bounds']['y']
    marks = link(world,'safety_markings_and_launch_pad')
    props = link(world,'signs_and_shipping_staging')
    for zone, aisle in aisles.items():
        bank, y, width = (aisle[key] for key in ('bank','center','width'))
        x = (bank.start + bank.end)/2
        for side in (-1,1):
            bank.add(marks,f'{zone}_stripe_{side}',(x,y+side*(width/2-.22),.009),
                     (bank.end-bank.start,.09,.012),YELLOW if aisle['functional'] else WHITE)
        along = bank.end-.04 if bank.name=='west-sort' else bank.start+.25
        sign_at = bank.point(along,y,spec['rack']['height']+.34)
        yaw = (pi/2 if bank.name=='west-sort' else -pi/2) if bank.axis=='x' else 0.
        texture_label(props,variant,f'aisle-{zone}',sign_at,(1.75,.46),yaw)

    rng = Random(spec['seed']+60)
    for area in spec['staging']:
        x,y = area['center']
        width,depth = area['size']
        tag = area['name']
        for side in (-1,1):
            box(marks,f'{tag}_line_{side}',(x,y+side*depth/2,.013),(width,.11,.015),accent)
            box(marks,f'{tag}_edge_{side}',(x+side*width/2,y,.013),(.11,depth,.015),accent)
        texture_label(props,variant,tag,(x,y+depth*.40,3.48),(2.98,.78))
        for j in range(max(2,int(depth/2.1))):
            py = y + (j-(floor(depth/2.1)-1)/2)*1.68
            for side in (-1,1):
                cargo(props,f'staged_{tag}_{j}_{side}',x+side*width*.26,py,.004,rng,collision=True)
        if area['usage']=='lifts':
            fork = link(world,'service_lift_prop')
            box(fork,'chassis',(x,y, .43),(.96,1.42,.59),YELLOW,True)
            box(fork,'roll_cage',(x,y+.11,1.84),(.89,.76,.12),STEEL,True)
            for a in (-1,1):
                box(fork,f'mast_{a}',(x+a*.33,y-.55,1.20),(.12,.21,2.40),STEEL,True)
                box(fork,f'fork_{a}',(x+a*.29,y-1.15,.14),(.12,1.11,.08),STEEL,True)
    if variant=='logistics-hub':
        for i in range(13):
            box(marks,f'crosswalk_{i}',(34.7+i*.43,-4.,.015),(.24,2.65,.015),WHITE)
            box(marks,f'transfer_dash_{i}',(34.4,y0+3.5+i*3.9,.014),(.085,1.53,.015),YELLOW)
    dx,dy, _ = profile['nodes']['dock']
    box(marks,'dock_baseline',(dx,dy,.011),(3.24,2.86,.014),accent)
    for side in (-1,1):
        box(marks,f'dock_line_{side}',(dx+side*1.58,dy,.023),(.08,2.83,.012),WHITE)
    fixture = link(world,'dock_service_equipment')
    box(fixture,'power_cabinet',(dx-1.98,dy+.20,.87),(.53,.94,1.74),frame,True)
    lateral = -1 if variant=='logistics-hub' else 1
    box(fixture,'network_cabinet',(dx-.28,dy+1.84*lateral,.67),(.88,.43,1.34),frame,True)
    box(fixture,'bench',(dx+1.08,dy+1.86*lateral,.53),(1.2,.54,1.06),accent,True)
    texture_label(fixture,variant,'dock-id',(dx-1.78,dy+.20,2.18),(2.28,.60),pi/2)
    texture_label(props,variant,'hall-id',(x0+.14,(y0+y1)/2,spec['bounds']['height']*.64),(5.6,1.48),pi/2)


def safety_geometry(world, spec, aisles, profile):
    towers, fields = [], {}
    for zone in FUNCTIONAL:
        aisle = aisles[zone]
        bank, center, width = (aisle[k] for k in ('bank','center','width'))
        fields[zone] = [bank.start-.35,center-width/2,bank.end+.35,center+width/2]
        for side, x in (('west',bank.start-.55),('east',bank.end+.55)):
            y = center+.35
            towers.append((zone,side,x,y,center,-pi/2))
    dx,dy,_ = profile['nodes']['dock']
    trunk = profile['nodes']['junction'][0]
    transfer = [trunk-1.02,min(fields[key][1] for key in FUNCTIONAL),trunk+1.02,dy+1.0]
    fields['T'] = transfer
    towers.append(('T','pad',trunk+.93,dy-2.30,dy,0.))
    towers.append(('D','tech',dx+1.44,dy+.82,dy,0.))
    for zone, side, x, y, _, _ in towers:
        parent = link(world,f'safety_{zone.lower()}_{side}')
        for part,z,size,color in SIGNAL_STACK:
            box(parent,part,(x,y,z),size,color,collision=part in {'foot','pole','housing'})
    x0,_ = spec['bounds']['x']
    y0,_ = spec['bounds']['y']
    wx,wy = x0+2.25,y0+2.40
    worker = link(world,'safety_worker',numbers((wx,wy,0.,0.,0.,0.)))
    navy = (.08,.17,.23)
    for sign in (-1,1):
        box(worker,f'boot_{sign}',(.02,sign*.12,.08),(.29,.16,.15),CHARCOAL)
        box(worker,f'leg_{sign}',(0,sign*.12,.45),(.16,.15,.69),navy)
        box(worker,f'arm_{sign}',(0,sign*.27,1.17),(.175,.13,.55),navy)
    box(worker,'vest',(0,0,1.14),(.255,.41,.51),YELLOW)
    box(worker,'reflective',(0,0,1.03),(.267,.42,.07),WHITE)
    box(worker,'head',(0,0,1.58),(.24,.24,.24),(.58,.38,.25))
    box(worker,'hardhat',(0,0,1.73),(.28,.27,.105),YELLOW)
    box(worker,'person',(0,0,.89),(.30,.53,1.78),collision=True)
    publisher = add(world.find("model[@name='safety_worker']"), 'plugin',
                    filename='ignition-gazebo-pose-publisher-system', name='ignition::gazebo::systems::PosePublisher')
    for tag,value in (('publish_link_pose','false'),('publish_model_pose','true'),
                      ('use_pose_vector_msg','true'),('update_frequency',15)):
        add(publisher,tag,value)
    overview = link(world,'safety_overview')
    camera = add(overview,'sensor',name='warehouse_access',type='camera')
    add(camera,'pose',numbers((dx-1,dy+1,profile['nodes']['shaft'][2]+.85,0.,.66,-.62)))
    add(camera,'always_on','true')
    add(camera,'update_rate',5)
    add(camera,'topic','/rackonaut_safety/overview')
    lens = add(camera,'camera')
    add(lens,'horizontal_fov',1.70)
    image = add(lens,'image')
    for key,value in (('width',800),('height',450),('format','R8G8B8')):
        add(image,key,value)
    clip = add(lens,'clip')
    add(clip,'near',.12)
    add(clip,'far',110)
    return fields,towers


def compile_environment(spec, target):
    banks = [Bank(**bank) for bank in spec['banks']]
    aisles = aisle_data(spec,banks)
    sdf,world = world_base()
    for lamp in world.findall('light')[1:]:
        world.remove(lamp)
    shell(world,spec)
    rig = AerialRig(world,spec,aisles)
    aerial = rig.profile
    ground(world,spec,aisles,aerial)
    aerial['dock'] = charging_station(world,tuple(aerial['nodes']['dock'][:2]))
    localization_infrastructure(world,aerial['nodes']['dock'][:2])
    registry = rack_rows(world,spec,banks,aisles)
    fields,towers = safety_geometry(world,spec,aisles,aerial)
    aerial['scene'] = twin_geometry(world,towers)
    variant = spec['id']
    textures_for(target/'library'/'rackonaut_warehouse_library'/variant,spec,aisles,registry)
    config = target/'config'
    config.mkdir(parents=True,exist_ok=True)
    worlds = target/'worlds'
    worlds.mkdir(parents=True,exist_ok=True)
    prefix = variant.replace('-','_')+'_'
    ET.indent(sdf,space='  ')
    ET.ElementTree(sdf).write(worlds/f'{prefix}localization_showcase.sdf',encoding='utf-8',xml_declaration=True)
    x0,x1 = spec['bounds']['x']
    y0,y1 = spec['bounds']['y']
    sizes = [{'name':name,'axis':a['axis'],'center':a['center'],'length':a['bank'].end-a['bank'].start,
              'width':a['width'],'functional':a['functional'], 'bank':a['bank'].name} for name,a in aisles.items()]
    depth = spec['rack']['depth']
    rows = []
    for bank in banks:
        for y in bank.rows:
            x,cy,_ = bank.point(bank.start,y-depth/2,0.)
            width,height,_ = bank.point(bank.end-bank.start,depth,0.)
            rows.append(dict(x=x,y=cy,width=width,height=height,bays=bank.bays,axis=bank.axis))
    layout = {'floor':dict(x=x0,y=y0,width=x1-x0,height=y1-y0),'racks':rows,
              'aisles':[{**a,'id':a['name'],'y':a['center']} for a in sizes if a['axis']=='x'],
              'pad':aerial['pad'],'takeoff_z':aerial['nodes']['shaft'][2],'crossing_x':spec['flight']['trunk_x'],
              'scene':aerial['scene'],
              'slots':{row['slot_id']:{key:row[key] for key in ('label','viewpoint','bay_center','bay_width','aisle','bay','level')}
                       for row in registry}}
    inventory = {'source':'mock_sap', 'locations':[{'slot_id':row['slot_id'],'pallet_id':row['expected']} for row in registry]}
    units = sorted({row[key] for row in registry for key in ('pallet','expected') if row[key]})
    sap = {**inventory,'synthetic':True,'warehouse_variant':variant,'handling_units':[
        {'hu_id':hu,'sku':f'KIT-{hu[1:]}','product_name':'Industrial maintenance kit','batch':variant.upper(),
         'lifecycle_status':'ACTIVE','quality_status':'RELEASED','stock_status':'ON_HAND'} for hu in units]}
    metadata = {'warehouse_variant':variant,'title':spec['title'],'schema_version':1,
                'bounds':spec['bounds'],'rack':spec['rack'],'banks':spec['banks'],'aisles':sizes,'staging':spec['staging'],
                'rack_rows':len(rows),'functional_slots':len(registry),'decorative_stock_has_no_inventory_ids':True,
                'tunnel_height_m':aerial['nodes']['shaft'][2],'dock':aerial['nodes']['dock'],
                'portal_opening_m':[PORTAL_WIDTH,PORTAL_WIDTH],
                'world_counts':{key:len(world.findall(query)) for key,query in
                                {'models':'model','visuals':'model/link/visual','collisions':'model/link/collision',
                                 'lights':'light'}.items()}}
    markers = {'dictionary':'DICT_4X4_50','locations':{str(row['marker']):row['slot_id'] for row in registry},
               'pallets':{str(row['pallet_marker']):row['pallet'] for row in registry if row['pallet_marker'] is not None}}
    for name,data in {'aerial_layout':aerial,'control_layout':layout,'safety_fields':fields,'control_markers':markers,
                      'mock_sap':sap,'dock_layout':aerial['dock'],'environment':metadata,
                      'ground_truth':{'source':'simulation_ground_truth', 'slots':registry}}.items():
        dump(config/f'{prefix}{name}.json',data)


def generate_variant(variant, output):
    path = Path(__file__).resolve().parents[1]/'environments'/f'{variant}.json'
    compile_environment(json.loads(path.read_text()),output)

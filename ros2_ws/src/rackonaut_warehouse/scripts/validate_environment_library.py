#!/usr/bin/env python3
"""Validate the generated environment assets and the existing protected graph offline."""

import argparse
import hashlib
import json
from itertools import combinations
from math import cos, dist, sin
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
from rackonaut_energy.aerial import Network
from rackonaut_energy.model import Model, estimate

from environment_library import BODY_HALF_HEIGHT, BODY_RADIUS, HALF_ENVELOPE, PORTAL_WIDTH, PROFILES


SOURCE = Path(__file__).resolve().parents[1]
PADDING = (BODY_RADIUS, BODY_RADIUS, BODY_HALF_HEIGHT)


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def xyz(text):
    return [float(value) for value in text.split()]


def expand(volume):
    return [*(a-b for a,b in zip(volume[:3],PADDING)),*(a+b for a,b in zip(volume[3:],PADDING))]


def overlap(a,b):
    return all(min(a[i+3],b[i+3])-max(a[i],b[i]) > 1e-5 for i in range(3))


def bounds(center, size):
    return [*(p-s/2 for p,s in zip(center,size)),*(p+s/2 for p,s in zip(center,size))]


def volumes(world, role):
    result = []
    for model in world.findall('model'):
        parent = xyz(model.findtext('pose','0 0 0 0 0 0'))
        assert parent[3:] == [0,0,0], model.get('name')
        for item in model.findall(f'link/{role}'):
            pose = xyz(item.findtext('pose','0 0 0 0 0 0'))
            size = item.findtext('geometry/box/size')
            if size:
                assert pose[3:] == [0,0,0], item.get('name')
                dimensions = xyz(size)
            elif role == 'visual' and item.findtext('geometry/mesh/uri','').endswith('/placard.obj'):
                width, _, height = xyz(item.findtext('geometry/mesh/scale'))
                dimensions = [abs(cos(pose[5]))*width+.005,abs(sin(pose[5]))*width+.005,height]
            else:
                continue
            result.append((model.get('name'),item.get('name'),bounds([a+b for a,b in zip(parent,pose)],dimensions)))
    return result


def marker_ids(path):
    image = cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
    assert image is not None,path
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detect = (aruco.ArucoDetector(dictionary).detectMarkers if hasattr(aruco,'ArucoDetector')
              else lambda image: aruco.detectMarkers(image,dictionary))
    _, markers, _ = detect(image)
    return [] if markers is None else sorted(int(x) for x in markers.ravel())


def assert_resources(world,root):
    for tag in ('uri','albedo_map'):
        for child in world.iter(tag):
            uri = child.text.removeprefix('model://')
            if uri.startswith('rackonaut_warehouse_library/'):
                path = root/'library'/uri
            else:
                assert uri.startswith('rackonaut_warehouse/'),uri
                path = SOURCE/uri.split('/',1)[1]
            assert path.is_file(),path


def graph_checks(network,profile,slots):
    model = Model(hover=.26,movement=.19,climb=.52)
    result = []
    for slot,row in slots.items():
        zone = row['aisle']
        pose = (*row['viewpoint'][:3],1.5707963267948966)
        outward = [leg.pose for leg in network.sortie(pose,zone)]
        homeward = [network.nodes[f'foot_{zone}'],*(leg.pose for leg in network.path(f'foot_{zone}','dock',returning=True))]
        round_trip = [network.nodes['dock'],*outward,*homeward]
        assert set(network.required([list(p[:3]) for p in round_trip])) == {'D',zone},slot
        assert all(network.allows(a,b,('D',zone)) for a,b in zip(round_trip,round_trip[1:])),slot
        assert not network.allows(network.nodes[f'entry_{zone}'],network.nodes[f'foot_{zone}'],('D',)),slot
        battery, duration = estimate(model,round_trip[0],round_trip[1:],scan_seconds=3.)
        result.append({'slot':slot,'viewpoint_z_m':pose[2],
                       'distance_m':round(sum(dist(a[:3],b[:3]) for a,b in zip(round_trip,round_trip[1:])),3),
                       'sim_s':round(duration,3),'required_pct_including_reserve':round(battery+model.reserve,3),
                       'within_100_percent':battery+model.reserve <= 100})
    return result


def validate(root,variant):
    prefix = variant.replace('-','_')+'_'
    world_file = root/'worlds'/f'{prefix}localization_showcase.sdf'
    world = ET.parse(world_file).getroot().find('world')
    assert world.get('name')=='rackonaut'
    data = {name:load(root/'config'/f'{prefix}{name}.json') for name in
            ('environment','aerial_layout','control_layout','control_markers','mock_sap','safety_fields','ground_truth')}
    metadata,profile = data['environment'],data['aerial_layout']
    network = Network(profile)
    assert data['control_layout']['pad']==profile['pad']
    assert set(data['safety_fields'])=={'A','B','T'}
    assert_resources(world,root)
    for model in world.findall('model'):
        for role in ('visual','collision'):
            fields = [item.get('name') for item in model.findall(f'link/{role}')]
            assert len(set(fields))==len(fields),(model.get('name'),role)
    shapes = {kind:volumes(world,kind) for kind in ('visual','collision')}
    tested = [(f'{a}→{b}',kind,expand(box)) for a,b,kind,box in network.edges]
    tested += [(f'aisle {zone}',zone,expand(box)) for zone,box in profile['inspection_volumes'].items()]
    for label,kind,swept in tested:
        for role, parts in shapes.items():
            for model,name,shape in parts:
                if kind=='shaft' and (name in {'floor','floor_collision','dock_contact_surface_collision'}
                        or (model=='safety_markings_and_launch_pad' and name.startswith('dock_'))
                        or (model=='rackonaut_dock' and name in {'landing_surface','home_-1','home_1','home_crossbar','coupler_-1','coupler_1'})):
                    continue
                assert not overlap(swept,shape),(variant,label,role,model,name,swept,shape)
    dock = world.find("model[@name='rackonaut_dock']/link")
    assert dock.findtext("sensor[@name='dock_presence']/contact/collision")=='dock_contact_surface_collision'
    plate = dock.find("collision[@name='dock_contact_surface_collision']")
    assert xyz(plate.findtext('pose'))[:2]==profile['nodes']['dock'][:2]
    assert abs(xyz(plate.findtext('pose'))[2]+xyz(plate.findtext('geometry/box/size'))[2]/2-.004)<1e-7
    markers = data['control_markers']
    used = {int(value) for group in ('locations','pallets') for value in markers[group]}
    assert len(used)==len(markers['locations'])+len(markers['pallets']) and max(used)<50
    slots = data['control_layout']['slots']
    expected = {item['slot_id']:item['pallet_id'] for item in data['mock_sap']['locations']}
    catalog = {item['hu_id'] for item in data['mock_sap']['handling_units']}
    occupied = [item['pallet'] for item in data['ground_truth']['slots'] if item['pallet']]
    assert set(expected)==set(slots)==set(markers['locations'].values())
    assert len(set(occupied))==len(occupied) and len(set(expected.values())-{None})==len(expected)
    assert all(row is not None for row in expected.values()) and set(expected.values())<=catalog
    png = root/'library'/'rackonaut_warehouse_library'/variant
    for row in data['ground_truth']['slots']:
        slot,mark = row['slot_id'],row['marker']
        assert markers['locations'][str(mark)]==slot and marker_ids(png/f'loc-{slot}.png')==[mark]
        assert row['expected']==expected[slot] and (row['pallet'] is None or row['pallet'] in catalog)
        if row['pallet']:
            hu = row['pallet_marker']
            assert marker_ids(png/f'hu-{slot}.png')==([hu] if hu is not None else [])
            if hu is not None:
                assert markers['pallets'][str(hu)]==row['pallet']
        else:
            assert not (png/f'hu-{slot}.png').exists()
    forecasts = graph_checks(network,profile,slots)
    return {**metadata,'sdf_bytes':world_file.stat().st_size,'sha256':hashlib.sha256(world_file.read_bytes()).hexdigest(),
            'clearance':{'checked_volumes':len(tested),'visual_intersections':0,'collision_intersections':0,
                         'portal_margin_per_side_m':round(PORTAL_WIDTH/2-HALF_ENVELOPE-BODY_RADIUS,3),
                         'inspection_margin_per_side_m':round(min(a['width']/2-.66-BODY_RADIUS for a in metadata['aisles']
                                                                if a['functional']),3)},
            'decoded_marker_ids':sorted(used),'route_energy_forecasts':forecasts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path,help='generated environment root or installed warehouse share')
    args = parser.parse_args()
    results = [validate(args.root,variant) for variant in PROFILES]
    for first,second in combinations(results,2):
        assert not set(first['decoded_marker_ids']) & set(second['decoded_marker_ids'])
    historical_assets = {int(path.stem.split('_')[1]) for path in (SOURCE/'materials/textures').glob('pallet_*.png')}
    historical_assets |= {int(path.stem.split('_')[1]) for path in (SOURCE/'materials/textures').glob('slot_*.png')}
    assert all(not set(result['decoded_marker_ids']) & historical_assets for result in results)
    print(json.dumps(results,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()

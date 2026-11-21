"""Guard the font provenance, paired pixel raster, and the reviewed DXE text report."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from dxe_text_trace import font, expected_surface, eye_rgb, pixel_offset
from run_dxe_text_once import EXPECTED_RASTER, validate_reports
from run_dxe_text_upright_once import EYE_RGB, NATIVE_BGR, validate_reports as validate_upright
from sec_dxe_qemu import screen


class FontTests(unittest.TestCase):
    def test_all_printable_ascii_matches_edk2(self):
        p=ROOT/'OculusGoPkg/Include/third-party/edk2/ConsoleFont.h'
        rows=re.findall(r'\{([^}]+)\},  // U\+([\dA-F]{4})',p.read_text())
        self.assertEqual([int(code,16) for _,code in rows],list(range(32,127)))
        for data,code in rows:
            pixels=bytes(int(x,16) for x in re.findall(r'0x[\da-f]{2}',data))
            self.assertEqual(pixels,font()[chr(int(code,16))])

    def test_required_drawing_glyphs(self):
        upstream=(ROOT/'edk2/MdeModulePkg/Universal/Console/GraphicsConsoleDxe/LaffStd.c').read_text()
        interface=(ROOT/'edk2/MdePkg/Include/Protocol/SimpleTextOut.h').read_text()
        adapted=(ROOT/'OculusGoPkg/Include/third-party/edk2/ConsoleFont.h').read_text()
        def shapes(pairs):
            return {name:bytes(int(x,16) for x in re.findall(r'0x[\da-fA-F]{2}',raw)) for name,raw in pairs}
        original=shapes(re.findall(r'\(CHAR16\)(\w+),\s*0x00,\s*\{([^}]+)\}',upstream))
        required=set(re.findall(r'#define\s+((?:BOXDRAW|BLOCKELEMENT|GEOMETRICSHAPE|ARROW)_\w+)\s+0x',interface))
        actual=shapes(re.findall(r'\{ (\w+), \{ ([^}]+) \} \}',adapted))
        self.assertEqual(required,set(actual))
        self.assertEqual(original,actual)

    def test_one_eye_pixel_error(self):
        data=expected_surface(screen('gop-blt'))
        self.assertEqual(sha256(eye_rgb(data,0)).hexdigest(), EYE_RGB)
        data[pixel_offset(1,4,12)] ^= 255
        self.assertNotEqual(eye_rgb(data,0),eye_rgb(data,1))

    def test_historical_capture_after_half_turn(self):
        # Read using the old 7-column physical screenshot coordinates, reflected
        # across *each* 1440x1280 half. This preserves the real Go text as an anchor.
        from sec_c_qemu import GUARD
        from verify_sec_visual_data import STRIDE
        surface = expected_surface(screen('gop-blt'))
        for eye in (0,1):
            rgb = bytearray()
            for v in range(76):
                for u in range(112):
                    old_x, old_y = 663+v, 592+111-u
                    origin = GUARD + (eye*1280+1279-old_y)*STRIDE + (1439-old_x)*3
                    rgb.extend(surface[origin:origin+3][::-1])
            self.assertEqual(sha256(rgb).hexdigest(), EXPECTED_RASTER)


class TextReview(unittest.TestCase):
    def setUp(self):
        self.report=json.loads((ROOT/'docs/evidence/dxe-text-qemu-20261120.json').read_bytes())
        self.static={**self.report,'result':'PASS-STATIC-DXE-TEXT'}
        self.row=next(r for r in self.report['cases'] if r['case']=='valid')

    def validate(self):
        validate_reports(self.report,self.static,self.report['fdSha256'])

    def test_model(self):
        self.validate()

    def test_swapped_raster(self):
        self.row['eyeRgbSha256']='0'*64
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_second_eye(self):
        self.row['glyphUploads']=14
        with self.assertRaises(ValueError):
            self.validate()


class UprightReview(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT/'docs/evidence/dxe-text-upright-qemu-20261120.json').read_bytes())
        self.static = {**self.report, 'result':'PASS-STATIC-DXE-TEXT'}
        self.row = next(r for r in self.report['cases'] if r['case']=='valid')

    def validate(self):
        validate_upright(self.report, self.static, self.report['fdSha256'])

    def test_native_and_optical_rasters(self):
        self.validate()
        self.assertEqual(self.row['nativeBgrSha256'], NATIVE_BGR)

    def test_reject_transformed_capture_with_old_native_scanout(self):
        self.row['nativeBgrSha256'] = '0'*64
        with self.assertRaises(ValueError):
            self.validate()

    def test_reject_unmarked_lines(self):
        self.row['textLines'] = ['EDK2 GO', 'UEFI 42']
        with self.assertRaises(ValueError):
            self.validate()

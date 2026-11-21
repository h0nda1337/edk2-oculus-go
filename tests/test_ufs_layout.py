"""Exercise the physical collector against a local fixture without a USB connection."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import collect_ufs_layout as collector
from logo_disk_qemu import disk


class PacificLayout(unittest.TestCase):
    def test_sysfs_partition_matches_exactly_two_gpt_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            medium = root / "gpt.raw"
            fixture = root / "mock-adb"
            fixture.write_bytes(b"offline")
            size = 34226176
            disk(medium, bytes(size), "splash", sector=4096)
            sysblock = "/sys/class/block/sde"
            base = "/sys/bus/platform/devices/624000.ufshc/"
            answers = {
                ("devices",): "List of devices attached\nTEST\tdevice",
                ("shell", "getprop", "ro.serialno"): "TEST",
                ("shell", "getprop", "ro.product.device"): "pacific",
                ("shell", "id", "-u"): "0",
                ("shell", "readlink", "-f", "/dev/block/bootdevice/by-name/splash"): "/dev/block/sde34",
                ("shell", "readlink", "-f", sysblock + "/device"): "/sys/devices/soc/624000.ufshc/host0/target0:0:0/0:0:0:4",
                ("shell", "cat", sysblock + "/queue/logical_block_size"): "4096",
                ("shell", "cat", sysblock + "/size"): str(medium.stat().st_size // 512),
                ("shell", "cat", sysblock + "34/start"): str(2048 * 8),
                ("shell", "cat", sysblock + "34/size"): str(size // 512),
            }
            reads = []

            def fake(argv, **kwargs):
                self.assertEqual(argv[:3], [str(fixture), "-s", "TEST"])
                cmd = tuple(argv[3:])
                if cmd[:4] == ("exec-out", "dd", "if=/dev/block/sde", "bs=4096"):
                    self.assertEqual(cmd[6:], ("2>/dev/null",))
                    skip, count = (int(v.split("=")[1]) for v in cmd[4:6])
                    reads.append((skip, count))
                    with medium.open("rb") as f:
                        f.seek(skip * 4096)
                        data = f.read(count * 4096)
                elif cmd in answers:
                    data = answers[cmd].encode()
                elif cmd in {("shell", "cat", base + "power/runtime_status"),
                             ("shell", "cat", base + "dma_mask_bits"), ("shell", "readlink", base + "iommu_group")}:
                    return subprocess.CompletedProcess(argv, 1, b"", b"absent")
                else:
                    self.fail(f"Unexpected operation: {cmd}")
                return subprocess.CompletedProcess(argv, 0, data, b"")

            with patch.object(collector, "ADB_SHA256", hashlib.sha256(b"offline").hexdigest()), \
                 patch.object(collector.subprocess, "run", side_effect=fake), contextlib.redirect_stdout(io.StringIO()):
                out = root / "out"
                collector.collect(fixture, "TEST", out)
                self.assertEqual(reads, [(1, 1), (2, 4)])
                report = json.loads((out / "layout.json").read_text())
                self.assertEqual((report["start"], report["splashBytes"]), (2048, size))
                self.assertEqual(report["iommuGroupLink"], "UNKNOWN")
                answers[("shell", "cat", sysblock + "34/start")] = "0"
                with self.assertRaisesRegex(ValueError, "partition bounds"):
                    collector.collect(fixture, "TEST", root / "mismatch")

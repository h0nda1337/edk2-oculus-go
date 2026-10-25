# Preserved partition inventory

The original backup captured 50 partitions, 6,620,180,480 bytes total, excluding
userdata. Names, block paths, sizes and hashes are retained in the machine-
readable `evidence/partitions.json`. These are imported backup records, not
new readbacks or a new verification of every dump. Actual images remain local
in the previous project's ignored dumps directory.

The observed by-name path is `/dev/block/bootdevice/by-name`; Android did not
expose `/dev/block/by-name`. The device uses UFS and A/B boot partitions.
No recovery, vendor, dtbo or vbmeta partition was found, with or without A/B
suffix. CNC and EVT DTBs were appended to each stock boot kernel component.

| Group | Likely purpose | Modify | Risk |
| --- | --- | --- | --- |
| boot_a / boot_b | Android kernel/ramdisk/appended DTBs | No | HIGH |
| system_a / system_b | Android root filesystems | No | HIGH |
| xbl, aboot, rpm, tz, hyp, devcfg, cmnlib, cmnlib64, keymaster, ovrtz, pmic | Boot/security/power firmware, exact per-name roles vary | No | CRITICAL |
| persist, modemst, fsg, keystore, sec, devinfo, cdt, ddr | Calibration/security/device state or boot configuration | No | CRITICAL |
| modem, bluetooth | Peripheral firmware | No | HIGH |
| misc, frp | Boot-control / protection metadata | No | HIGH |
| Remaining names | UNKNOWN until separately reviewed | No | CRITICAL by default |

Hashes identify historical originals; they are not authorization to restore
or write them. Consult RECOVERY.md and the full original inventory before a
future separately disclosed permanent operation. This reconstruction neither
changes partitions nor includes a flashing script.

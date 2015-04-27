import arcpy

import paths
import sys

"""
Exports each visible layer in the map file to PNG
"""

if len(sys.argv) == 1:
    outdir = paths.images
else:
    outdir = sys.argv[1]

mapdoc = paths.joinNative(paths.projRoot, "dev.mxd")
print mapdoc
mxd = arcpy.mapping.MapDocument(mapdoc)
df = arcpy.mapping.ListDataFrames(mxd, "")[0]
df.extent = arcpy.Describe(paths.studyArea).extent

aspect = (df.extent.XMax - df.extent.XMin) / float(df.extent.YMax - df.extent.YMin)
outHeight = 1600
outWidth = int(outHeight * aspect)
print "Aspect: {} --> {} x {}".format(aspect, outWidth, outHeight)

# turn off layers
print "Turning off layers..."
layers = [ layer for layer in arcpy.mapping.ListLayers(mxd, "", df) if layer.visible ]
for lyr in layers:
    lyr.visible = False
# mxd.save()

# output each
for lyr in layers:
    lyr.visible = True
    # mxd.save()
    dest = paths.joinNative(outdir, lyr.name + ".png")
    print "Exporting {} to {}".format(lyr.name, dest)
    arcpy.mapping.ExportToPNG(mxd,
                              dest,
                              df,
                              outWidth,
                              outHeight,
                              96, False, "24-BIT_TRUE_COLOR", "255, 255, 255", "255, 255, 255", False )

    lyr.visible = False
    # mxd.save()

# for lyr in layers:
#     lyr.visible = True
# mxd.save()

del mxd

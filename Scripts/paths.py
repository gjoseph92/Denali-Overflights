import os
import shutil

#############################
## Paths to things we'll need

def join(*paths):
	return '/'.join(paths)

def joinNative(*paths):
	paths = [path.replace('/', os.sep) for path in paths]
	return os.path.join(*paths)

projRoot = os.path.normpath( os.path.join(os.getcwd(), "..") ).replace(os.sep, '/')
# ArcPy uses forward slash paths somehow. It's all that seems to work
# Update: spatial analyst uses forward slashes, some of ArcPy does too. But not arcpy.mapping.

resistances = join(projRoot, "Inputs", "Resistances.gdb")
inputFeatures = join(projRoot, "Inputs", "Features.gdb")
# studyArea = join(inputFeatures, "Cost_Distance_Study_Area")
studyArea = join(inputFeatures, "Study_Area_Clipped")
airports = join(inputFeatures, "airports")
sources = join(inputFeatures, "sources")
destination = join(inputFeatures, "destination")
cscapeGrounds = join(projRoot, "Inputs", "Circuitscape", "grounds.asc")
cscapeSources = join(projRoot, "Inputs", "Circuitscape", "sources.asc")
alaskaAlbers = join(projRoot, "Cost Distance Layers", "Study_Area", "Alaska Albers Equal Area Conic.prj")
cscapeSettings = join(projRoot, "Circuitscape", "settingsTemplate.ini")
# mxdTemplate = joinNative(projRoot, "template.mxd")
mxdTemplate = joinNative(projRoot, "templateNoCscape.mxd")

workspace = join(projRoot, "Workspace.gdb")
toolbox = join(projRoot, "DenaliJobs.tbx")
costRasters = join(projRoot, "Results", "CostRasters")
LCPs = join(projRoot, "Results", "LCPs")
preprocessed = join(projRoot, "Results", "Preprocessed")
images = join(projRoot, "Results", "Images")
circuitscape = join(projRoot, "Results", "Circuitscape")

poster = join(projRoot, "Poster")

temp = "C:\\temp"

try:
	os.mkdir(temp)
except OSError:
	pass  # already exists

def setEnv(env):
	# use a local workspace so multiple workers don't lock on the same tempfile	
	env.workspace = temp
	env.scratchWorkspace = env.workspace
	env.cellSize = 500
	env.extent = studyArea
	env.outputCoordinateSystem = alaskaAlbers
	env.overwriteOutput = True

def cache(*paths, **kwargs):
	subdir = kwargs.get("subdir")
	cachedir = temp
	if subdir is not None:
		cachedir = joinNative(cachedir, subdir)
		if not os.path.isdir(cachedir):
			os.makedirs(cachedir)
	localpaths = []
	for path in paths:
		path = joinNative(path)
		filename = os.path.basename(path)
		localpath = os.path.join(cachedir, filename)
		try:
			shutil.copyfile(path, localpath)
		except IOError:
			localpath = None
		localpaths.append(localpath)

def dropcache(*paths):
	for path in paths:
		if path is None: continue
		if temp not in os.paths.dirname(path):
			print "{} is not in local cache, not deleting it".format(path)
		else:
			try:
				os.remove(path)
			except IOError as e:
				print "Couldn't remove {}".format(path)

def clearTemp():
	print "Clearing {}".format(temp)
	shutil.rmtree(temp)
	os.makedirs(temp)
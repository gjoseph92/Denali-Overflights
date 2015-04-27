import os

def run(configFile):
	path = get_cs_path()
	if path is None:
		raise ImportError("Couldn't find Circuitscape installation.")
	fail = call_circuitscape(path, configFile)
	if fail:
		raise RuntimeError("Circuitscape failed.")

# Taken from Circuitscape ArcGIS plugin
def get_cs_path():
    """Returns path to Circuitscape installation """
    envList = ["ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"]
    for x in range (0,len(envList)):
        try:
            pfPath = os.environ[envList[x]]
            csPath = os.path.join(pfPath,'Circuitscape\\cs_run.exe')
            if os.path.exists(csPath): return csPath
        except: pass
    return None

def call_circuitscape(CSPATH, outConfigFile):
    memFlag = False
    failFlag = False
    print('     Calling Circuitscape:')
    import subprocess
    proc = subprocess.Popen([CSPATH, outConfigFile],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                           shell=True)
    while proc.poll() is None:
        output = proc.stdout.readline()

        if 'Traceback' in output or 'RuntimeError' in output:
            print("\nCircuitscape failed.")
            failFlag = True
            if 'memory' in output:
                memFlag = True
        if ('Processing' not in output and 'laplacian' not in output and 
                'node_map' not in output and (('--' in output) or 
                ('sec' in output) or (failFlag == True))):
            print("      " + output.replace("\r\n",""))                
    
    # Catch any output lost if process closes too quickly
    output=proc.communicate()[0]
    for line in output.split('\r\n'):
        if 'Traceback' in line:
            print("\nCircuitscape failed.")
            if 'memory' in line:
                memFlag = True
        if ('Processing' not in line and 'laplacian' not in line and 
                'node_map' not in line and (('--' in line) or 
                ('sec' in line) or (failFlag == True))):
           print("      " + str(line))#.replace("\r\n","")))              
    return failFlag
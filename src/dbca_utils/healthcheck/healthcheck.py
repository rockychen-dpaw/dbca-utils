import os
import importlib
from collections import OrderedDict
import logging
import psutil
import subprocess
import random
import re
import time
import socket
import requests
from datetime import datetime

from django.urls import reverse,path,include
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse,HttpResponseServerError
from django.core.signals import request_started
from django.core.cache import cache

logger = logging.getLogger(__name__)


#WORKLOADS means the number of WORKLOADS should be started.
#If WORKLOADS is dynamic, please don't set it.
HEALTHCHECK_ENABLED = os.environ.get("HEALTHCHECK_ENABLED","true").lower() == "true"
if not HEALTHCHECK_ENABLED:
    HEALTHCHECK_ENABLED = True if cache else None

HEALTHCHECK_SYSTEMDATA_ENABLED = os.environ.get("HEALTHCHECK_SYSTEMDATA_ENABLED","true").lower() == "true"
HEALTHCHECK_PROCESSDATA_ENABLED = os.environ.get("HEALTHCHECK_PROCESSDATA_ENABLED","true").lower() == "true"

CACHE_PREFIX = os.environ.get("CACHE_PREFIX","")
PORT = int(os.environ.get("WORKLOAD_PORT",8080))
WORKLOADS = int(os.environ.get("WORKLOADS",0))
WORKLOAD_DEPLOYMENT = os.environ.get("WORKLOAD_DEPLOYMENT","true").lower() == "true"
if WORKLOADS < 0 :
    WORKLOADS = 0
WORKLOAD_FAILED_THRESHOLD = int(os.environ.get("WORKLOAD_FAILED_THRESHOLD",2))

WORKLOAD_VOLUMES = os.environ.get("WORKLOAD_VOLUMES","automatic")

if not WORKLOAD_VOLUMES or WORKLOAD_VOLUMES.lower() in ("disabled","false"):
    WORKLOAD_VOLUMES_ENABLED = False
    WORKLOAD_VOLUMES = None
elif WORKLOAD_VOLUMES.lower() == "automatic":
    WORKLOAD_VOLUMES_ENABLED = True
    WORKLOAD_VOLUMES = None
else:
    WORKLOAD_VOLUMES = [v.strip() for v in WORKLOAD_VOLUMES.split(",") if v.strip()]
    WORKLOAD_VOLUMES_ENABLED = True if WORKLOAD_VOLUMES else False


RANDOM_CHARS="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYA0123456789~!@#$%^&*()-_+=`{}[];':\",./<>?"
RANDOM_CHARS_MAX_INDEX = len(RANDOM_CHARS) - 1

def generate_secret():
    return "".join(RANDOM_CHARS[random.randint(0,RANDOM_CHARS_MAX_INDEX)] for i in range(0,32))

secret = None

def get_workloadname(index):
    return "workload{}".format(index)

def get_local_ip():
    # Create a UDP socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to a dummy external IP (doesn't have to be reachable)
        s.connect(('192.168.1.1', 1))
        ip = s.getsockname()[0]
    except Exception:
        # Fallback to localhost if network is down
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

hostname = socket.gethostname()
if WORKLOAD_DEPLOYMENT:
    registerhostname = hostname
else:
    statefulset_hostname_re = re.compile("-(?P<index>\\d+)$")
    registerhostname = get_workloadname(statefulset_hostname_re.search(hostname).group("index"))

ip = get_local_ip()

item_version = "__version__"
key_workloads = "{}__workloads__".format(CACHE_PREFIX)
key_workloads_lock = "{}lock__".format(key_workloads)

def register_webappserver(*args,**kwargs):
    """
    Register a web server running in the same workload
    1. Write a server register file in workload's local file system
    2. Register the workload to a cache shared by all workloads
    """
    pid = os.getpid()
    global secret
    logger.debug("Register the webapp server '{}({}).{}'.".format(hostname,ip,pid))
    try:
        workloads_changed = False
        workloads = cache.get(key_workloads) or {item_version:0}
        if registerhostname not in workloads:
            #not registered by other webservers running in the same workload
            secret = generate_secret()
            workloads[registerhostname] = [[ip,PORT],secret,0]
            workloads_changed = True
        else:
            #already registered by other webservers, check whether the data is correct
            data = workloads[registerhostname]
            if not isinstance(data[0],list):
                data[0] = [ip,PORT]
                workloads_changed = True
            if data[0][0] != ip:
                data[0][0] = ip
                workloads_changed = True
            if data[0][1] != PORT:
                data[0][1] = PORT
                workloads_changed = True
            if data[2] != 0:
                data[2] = 0
                workloads_changed = True
            if workloads_changed:
                #workload data is changed.
                secret = generate_secret()
                data[1] = secret
            else:
                #workload data is not changed.
                secret = data[1]

        if workloads_changed:
            #save thw workloads data to cache
            save_workloads(workloads)
    
    except Exception as ex:
        logger.error("Failed to register the webapp webserver '{}({}).{}'. {}: {}".format(hostname,ip,pid,ex.__class__.__name__,str(ex)))
        #Failed to register workload, remove the server register file
        try:
            os.remove(registerfile)
        except Excepton as ex:
            if os.path.exists(registerfile):
                logger.error("Failed to remove webapp webserver register file '{}'.{}: {}".format(registerfile,ex.__class__.__name__,str(ex)))

        #ignore the exception
        return

    #register successfully, no need to register again.
    #disconnect the receiver, no need to register again.
    request_started.disconnect(dispatch_uid="register_webappserver")
    logger.debug("Successfully register the webserver({}<{}>:{}.{}) to the cache.".format(hostname,ip,PORT,pid))


#register the signal receiver to register the workload
#the signal receiver will be disconnected after successful registration
if HEALTHCHECK_ENABLED:
    #healthcheck is not initied
    request_started.connect(register_webappserver,dispatch_uid="register_webappserver")


VALID_WORKLOAD_VOLUMES = None
def get_volumes_healthdata():
    global VALID_WORKLOAD_VOLUMES
    try:
        if VALID_WORKLOAD_VOLUMES is None:
            volumes = []
            for partition in psutil.disk_partitions(all=True):
                if WORKLOAD_VOLUMES is None:
                    if partition.fstype.lower() not in ("cifs","nfs","sshfs","davfs2"):
                        continue
                    volumes.append(partition.mountpoint)
                elif partition.mountpoint in WORKLOAD_VOLUMES:
                    volumes.append(partition.mountpoint)

            VALID_WORKLOAD_VOLUMES = volumes

        if not VALID_WORKLOAD_VOLUMES:
            return {}

        volumesdata = {}
        for volume in VALID_WORKLOAD_VOLUMES:
            diskusage  = psutil.disk_usage(volume)
            if diskusage.total / 1073741824 >= 10:
                #large than 10G, use 'G' as unit
                volumesdata[volume] = {"size":round(diskusage.total / 1073741824),"used":round(diskusage.used / 1073741824),"pcent":100 * diskusage.used/diskusage.total,"unit":"G"} 
            elif diskusage.total / 1048576 >= 10:
                #large than 10M, use 'M' as unit
                volumesdata[volume] = {"size":round(diskusage.total / 1048576),"used":round(diskusage.used / 1048576),"pcent":100 * diskusage.used/diskusage.total,"unit":"M"} 
            else:
                volumesdata[volume] = {"size":round(diskusage.total / 1024),"used":round(diskusage.used / 1024),"pcent":100 * diskusage.used/diskusage.total,"unit":"K"} 

        return volumesdata
    except Exception as ex:
        import traceback;
        traceback.print_exc()
        return "Failed to volumes usage data.{}: {}".format(ex.__class__.__name__,str(ex))

def get_workload_system_healthdata():
    cpu_pcent = system_cpu_pcents = psutil.cpu_percent(percpu=False)
    cpucores_pcent = system_cpu_pcents = psutil.cpu_percent(percpu=True)
    memoryinfo = psutil.virtual_memory()
    netio = psutil.net_io_counters()

    return {
        "cpu_pcent":cpu_pcent,
        "cpucores_pcent":cpucores_pcent,
        "memory_total": memoryinfo.total / 1073741824,
        "memory_used": (memoryinfo.total - memoryinfo.available) / 1073741824,
        "memory_pcent": (memoryinfo.total - memoryinfo.available) * 100 / memoryinfo.total,
        "bytes_sent": netio.bytes_sent,
        "bytes_recv": netio.bytes_recv
    }

def get_process_healthdata(proc):
    memoryinfo = proc.memory_info()
    result = {
        "start_time":timezone.make_aware(datetime.fromtimestamp(proc.create_time())).strftime("%Y-%m-%dT%H:%M:%S"),
        "cpu_num": proc.cpu_num(),
        "cpu_pcent": proc.cpu_percent(),
        "pmemory":memoryinfo.rss / 1048576,
        "vmemory":memoryinfo.vms / 1048576
    }
    if settings.DEBUG:
        result["cmdline"] = proc.cmdline()
        if proc.pid == curprocpid:
            result["currentprocess"] = True

    return result

rootproc = None
curprocpid = None
def get_workload_app_healthdata(perprocess=True):
    """
    All processes belonging to the webapp should have
    1. same parent process
    2. the cmdline of all processes should be same
    """
    global rootproc
    global curprocpid
    if not curprocpid:
        curprocpid = os.getpid()

    if not rootproc:
        #the the root proc
        #get the pid of the current process
        curproc = psutil.Process(curprocpid)
        #find the parent
        pproc = curproc
        rootproc = None
        app_cmdline = curproc.cmdline()
        while not rootproc:
            ppid = pproc.ppid()
            if not ppid:
                rootproc = pproc
                continue
    
            tmpproc = psutil.Process(ppid)
            tmpproc_cmdline = tmpproc.cmdline()
            if tmpproc_cmdline == app_cmdline:
                #the pproc has the same cmd line as current proc. the pproc is also related app python process
                pproc = tmpproc
            elif any(any(key in p for key in ("python","gunicorn","uwsgi","django")) for p in tmpproc_cmdline):
                #the pproc is still the python process.
                pproc = tmpproc
            else:
                rootproc = pproc


    #find all realted processes and its health data
    rootproc_data = get_process_healthdata(rootproc)
    result = {
        "start_time": rootproc_data["start_time"],
        "cpu_total" : rootproc_data["cpu_pcent"],
        "cpu_min" : rootproc_data["cpu_pcent"],
        "cpu_max" : rootproc_data["cpu_pcent"],
        "pmemory_total" : rootproc_data["pmemory"],
        "pmemory_min" : rootproc_data["pmemory"],
        "pmemory_max" : rootproc_data["pmemory"],
        "vmemory_total" : rootproc_data["vmemory"],
        "vmemory_min" : rootproc_data["vmemory"],
        "vmemory_max" : rootproc_data["vmemory"],
        "processes" : 1
    }
    if perprocess:
        result["process"] = rootproc_data
        result["process"]["children"] = []

    processes = [(rootproc.children(),result["process"]["children"] if perprocess else None)]
    while processes:
        childproces,childrendatas = processes.pop(0)
        for childproc in childproces:
            childproc_data = get_process_healthdata(childproc)

            result["cpu_total"] += childproc_data["cpu_pcent"]
            if result["cpu_min"] > childproc_data["cpu_pcent"]:
                result["cpu_min"] = childproc_data["cpu_pcent"]
            if result["cpu_max"] < childproc_data["cpu_pcent"]:
                result["cpu_max"] = childproc_data["cpu_pcent"]

            result["pmemory_total"] += childproc_data["pmemory"]
            if result["pmemory_min"] > childproc_data["pmemory"]:
                result["pmemory_min"] = childproc_data["pmemory"]
            if result["pmemory_max"] < childproc_data["pmemory"]:
                result["pmemory_max"] = childproc_data["pmemory"]

            result["vmemory_total"] += childproc_data["vmemory"]
            if result["vmemory_min"] > childproc_data["vmemory"]:
                result["vmemory_min"] = childproc_data["vmemory"]
            if result["vmemory_max"] < childproc_data["vmemory"]:
                result["vmemory_max"] = childproc_data["vmemory"]

            result["processes"] += 1

            if perprocess:
                childrendatas.append(childproc_data)

            childproc_children = childproc.children()
            if childproc_children:
                if perprocess:
                    childproc_data["children"] = []
                processes.append((childproc_children,childproc_data["children"] if perprocess else None))

    return result

def get_workload_healthdata():
    try:
        result = {
            "resources": get_workload_app_healthdata(HEALTHCHECK_PROCESSDATA_ENABLED)
        }
        if HEALTHCHECK_SYSTEMDATA_ENABLED:
            result["system"] = get_workload_system_healthdata()

        if WORKLOAD_VOLUMES_ENABLED:
            result["volumes"] = get_volumes_healthdata()

        return (200,result)
    except Exception as ex:
        return (500,"{}:{}".format(ex.__classs__.__name__,str(ex)))

bearer_token_re = re.compile("^Bearer\\s+(?P<token>\\S+)\\s*$")
def get_auth_bearer(request):
    """
    Check the bearer authentication
    Return True if authenticated; otherwiser return False
    """
    bearer_auth = request.META.get('HTTP_AUTHORIZATION').strip() if 'HTTP_AUTHORIZATION' in request.META else ''
    m = bearer_token_re.search(bearer_auth)
    token = None
    if m:
        token = m.group('token')
    return token

key_assignedworkloads = "{}__assignedworkloads__".format(CACHE_PREFIX)
key_assignedworkloads_lock = "{}lock__".format(key_assignedworkloads)

def str_workloads(workloads):
    return ",".join(["{}={}:{}({})".format(host,data[0][0],data[0][1],data[2]) if host != item_version else "{}={}".format(host,data) for host,data in workloads.items()])


def save_workloads(workloads,unreached_servers=None):
    """
    Save the updated workloads to cache
    """
    #save the workloads
    logger.debug("Begin to save the changed workloads data({}) to cache.".format(str_workloads(workloads)))
    while True:
        if cache.add(key_workloads_lock, 1, timeout=1):
            #get the lock
            try:
                cur_workloads = cache.get(key_workloads)
                if cur_workloads and cur_workloads.get(item_version,0) != workloads[item_version]:
                    #workloads data was changed after fetching the workloads data
                    #add the new added workloads data
                    for k,v in cur_workloads.items():
                        if k == item_version:
                            continue
                        if k not in workloads and (not unreached_servers or k not in unreached_servers):
                            workloads[k] = v
                    if cur_workloads.get(item_version,0) == 0:
                        workloads[item_version] += 1
                    else:
                        workloads[item_version] = cur_workloads[item_version] + 1
                else:
                    #workloads data is not changed.
                    workloads[item_version] += 1

                #save the new workloads data
                cache.set(key_workloads,workloads,timeout=None)
                logger.debug("Successfully save the workloads:{}".format(str_workloads(workloads)))
                return
            finally:
                #release the lock
                cache.delete(key_workloads_lock)
        else:
            #already locked.,wait 100 milliseconds, and try again
            time.sleep(0.01)
            continue

def save_assignedworkloads(assignedworkloads):
    """
    Save the updated assigned workloads to cache
    """
    #save the workloads
    logger.debug("Begin to save the changed assigned workloads data({}) to cache.".format(assignedworkloads))
    while True:
        if cache.add(key_assignedworkloads_lock, 1, timeout=1):
            #get the lock
            try:
                cur_assignedworkloads = cache.get(key_assignedworkloads)
                if cur_assignedworkloads and cur_assignedworkloads.get(item_version,0) != assignedworkloads[item_version]:
                    #sync the latest cache data
                    for k,v in cur_assignedworkloads.items():
                        if k == item_version:
                            continue
                        if k not in assignedworkloads:
                            assignedworkloads[k] = v
                        elif v != assignedworkloads[k]:
                            assignedworkloads[k] = v

                    if cur_assignedworkloads.get(item_version,0) == 0:
                        assignedworkloads[item_version] += 1
                    else:
                        assignedworkloads[item_version] = cur_assignedworkloads[item_version] + 1
                else:
                    #workloads data is not changed.
                    assignedworkloads[item_version] += 1

                #save the new workloads data
                cache.set(key_assignedworkloads,assignedworkloads,timeout=None)
                logger.debug("Successfully save the assigned workloads:{}".format(assignedworkloads))
                return
            finally:
                #release the lock
                cache.delete(key_assignedworkloads_lock)
        else:
            #already locked.,wait 100 milliseconds, and try again
            time.sleep(0.01)
            continue

def populate_summary_data(datas):
    """
    Populate the resource summary data from workloads' resource usage data
    """
    summary = {
        "cpu_total":0,
        "cpu_min":None,
        "cpu_max":None,
        "process_cpu_min":None,
        "process_cpu_max":None,
        "pmemory_total":0,
        "pmemory_min":None,
        "pmemory_max":None,
        "process_pmemory_min":None,
        "process_pmemory_max":None,
        "vmemory_total":0,
        "vmemory_min":None,
        "vmemory_max":None,
        "process_vmemory_min":None,
        "process_vmemory_max":None,
        "processes_total":0,
        "workloads_running":0,
        "workloads_failed":0,
    }
    if settings.DEBUG:
        summary["currentworkload"] = registerhostname

    for servername,serverdata in datas.items():
        if isinstance(serverdata,str):
            summary["workloads_failed"] += 1
            continue
        summary["processes_total"] += serverdata["resources"]["processes"]

        summary["cpu_total"] += serverdata["resources"]["cpu_total"]

        summary["cpu_total"] += serverdata["resources"]["cpu_total"]
        if summary["cpu_min"] is None or summary["cpu_min"] > serverdata["resources"]["cpu_total"]:
            summary["cpu_min"] = serverdata["resources"]["cpu_total"]
        if summary["cpu_max"] is None or summary["cpu_max"] < serverdata["resources"]["cpu_total"]:
            summary["cpu_max"] = serverdata["resources"]["cpu_total"]
        if summary["process_cpu_min"] is None or summary["process_cpu_min"] > serverdata["resources"]["cpu_min"]:
            summary["process_cpu_min"] = serverdata["resources"]["cpu_min"]
        if summary["process_cpu_max"] is None or summary["process_cpu_max"] < serverdata["resources"]["cpu_max"]:
            summary["process_cpu_max"] = serverdata["resources"]["cpu_max"]

        summary["pmemory_total"] += serverdata["resources"]["pmemory_total"]
        if summary["pmemory_min"] is None or summary["pmemory_min"] > serverdata["resources"]["pmemory_total"]:
            summary["pmemory_min"] = serverdata["resources"]["pmemory_total"]
        if summary["pmemory_max"] is None or summary["pmemory_max"] < serverdata["resources"]["pmemory_total"]:
            summary["pmemory_max"] = serverdata["resources"]["pmemory_total"]
        if summary["process_pmemory_min"] is None or summary["process_pmemory_min"] > serverdata["resources"]["pmemory_min"]:
            summary["process_pmemory_min"] = serverdata["resources"]["pmemory_min"]
        if summary["process_pmemory_max"] is None or summary["process_pmemory_max"] < serverdata["resources"]["pmemory_max"]:
            summary["process_pmemory_max"] = serverdata["resources"]["pmemory_max"]

        summary["vmemory_total"] += serverdata["resources"]["vmemory_total"]
        if summary["vmemory_min"] is None or summary["vmemory_min"] > serverdata["resources"]["vmemory_total"]:
            summary["vmemory_min"] = serverdata["resources"]["vmemory_total"]
        if summary["vmemory_max"] is None or summary["vmemory_max"] < serverdata["resources"]["vmemory_total"]:
            summary["vmemory_max"] = serverdata["resources"]["vmemory_total"]
        if summary["process_vmemory_min"] is None or summary["process_vmemory_min"] > serverdata["resources"]["vmemory_min"]:
            summary["process_vmemory_min"] = serverdata["resources"]["vmemory_min"]
        if summary["process_vmemory_max"] is None or summary["process_vmemory_max"] < serverdata["resources"]["vmemory_max"]:
            summary["process_vmemory_max"] = serverdata["resources"]["vmemory_max"]

        summary["workloads_running"] += 1

    datas["summary"] = summary

workload_healthcheck_url = None
headers={"Authorization":None,"Accept": "application/json"}

def harvest_healthdata(request):
    global secret

    global workload_healthcheck_url
    if not workload_healthcheck_url:
        workload_healthcheck_url = reverse('healthcheck:workload_healthdata')

    workloads = cache.get(key_workloads) or {item_version:0}
    workloads_changed = False
    logger.debug("Get the workloads from cache :{}".format(str_workloads(workloads)))

    if registerhostname not in workloads:
        secret = generate_secret()
        workloads[registerhostname] = [[ip,PORT],secret,0]
        workloads_changed = True

    servers_res = {}
    unreached_servers = []
    #havest health data from all workloads
    for servername, serverdata in workloads.items():
        if servername == item_version:
            continue
        if servername == registerhostname:
            servers_res[servername] = get_workload_healthdata()
            continue

        serverip,port = serverdata[0]
        headers["Authorization"] = "Bearer {}".format(serverdata[1])
        headers["host"] = request.get_host()
        url = "http://{}:{}{}".format(serverip,port,workload_healthcheck_url)
        try:
            res = requests.get(url,headers=headers)
        except Exception as ex:
            #the server is offline, don't add the data to servers_res
            workloads_changed = True
            serverdata[2] += 1
            if serverdata[2] >= WORKLOAD_FAILED_THRESHOLD:
                #continuous failed times is greater than WORKLOAD_FAILED_THRESHOLD.
                unreached_servers.append(servername)
            servers_res[servername] = (-1,"{1}:{2},url={0}".format(url,ex.__class__.__name__,str(ex)))
            continue
        if res.status_code in (502,503,504):
            #the server is offline, don't add the data to servers_res
            workloads_changed = True
            serverdata[2] += 1
            if serverdata[2] >= WORKLOAD_FAILED_THRESHOLD:
                #continuous failed times is greater than WORKLOAD_FAILED_THRESHOLD.
                unreached_servers.append(servername)
            servers_res[servername] = (res.status_code,"{1}:{2},url={0}".format(url,res.status_code,res.text))
        elif res.status_code == 200:
            #the server is in good health, add the health data to servers_res
            servers_res[servername] = (200,res.json())
            if serverdata[2] > 0:
                serverdata[2] -= 1
                workloads_changed = True
        elif res.status_code == 599:
            #the server is in good health, add the health data to servers_res
            try:
                data = res.json()
                if data["status"] == 401:
                    #authentication error, caused by different workload.
                    workloads_changed = True
                    unreached_servers.append(servername)
                    servers_res[servername] = (503,"{1}:{2},url={0}".format(url,data["status"],data["message"]))
                else:
                    servers_res[servername] = (500,"{1}:{2}. url={0}".format(url,data["status"],data["message"]))
            except:
                workloads_changed = True
                unreached_servers.append(servername)
                servers_res[servername] = (503,"Web server is offline.url={0}".format(url))

        else:
            #unexpected error, caused by different workload
            workloads_changed = True
            unreached_servers.append(servername)
            servers_res[servername] = (500,"{1}:{2},url={0}".format(url,res.status_code,res.text))

    for servername in unreached_servers:
        del workloads[servername]

    logger.debug("healthdata harvest result :workloads={}, resources={}".format(workloads,servers_res))

    if workloads_changed:
        save_workloads(workloads,unreached_servers)

    return (workloads,servers_res)

OFFLINE_STATUSCODE_LIST = (502,503,504,401,403,-1)
if WORKLOADS > 0 and WORKLOAD_DEPLOYMENT:
    #has a fixed number of workloads and it is a deployment
    WORKLOADNAMES = [get_workloadname(index) for index in range(WORKLOADS)]
    def healthdata_view(request):
        #process the workloads which are alreasy assigned a workload name
        workloads,servers_res = harvest_healthdata(request)
        assignedworkloads = cache.get(key_assignedworkloads) or {item_version:1}
        logger.debug("Get assigned workloads:{}".format(assignedworkloads))
        datas = {}
        index = 0
        reassign_workloads = 0
        for workloadname in WORKLOADNAMES:
            servername = assignedworkloads.get(workloadname)
            if not servername:
                #workloadname is not assined to a server
                reassign_workloads += 1
                continue

            #workload name is assigned to a server
            if servername not in servers_res :
                #the server is not available
                reassign_workloads += 1
                continue

            datas[servername] = servers_res[servername]
            if servers_res[servername][0] in OFFLINE_STATUSCODE_LIST:
                #Related workload is offline, need to reassign another workload
                reassign_workloads += 1
            del servers_res[servername]

        assignedworkloads_changed = False
        if len(WORKLOADNAMES) != len(assignedworkloads):
            #remove the unexisted workloads from assignedworkloads.
            for key in [k for k in assignedworkloads.keys()]:
                if key == item_version:
                    continue
                if key not in WORKLOADNAMES:
                    assignedworkloads_changed = True
                    del assignedworkloads[key]

        if reassign_workloads > 0:
            #Some workloads are not assigned a workload name or are not available
            #Using the following to replace the exisint one with new one if possible
            #Step 1: Replace the unavailable server with a new one 
            #Step 2: Assign the new server to the missing assignedworkloads(missed in the assignedworkloads before)
            step = 0
            while reassign_workloads > 0:
                step += 1
                for workloadname in WORKLOADNAMES:
                    servername = assignedworkloads.get(workloadname)
                    if servername in datas and datas[servername][0] not in OFFLINE_STATUSCODE_LIST:
                        #related server is online.no need to reassign
                        continue
                    elif step == 1:
                        #step 1 only reassign the already assigned workloads
                        if workloadname not in assignedworkloads:
                            continue
                    replacedservername = None
                    for name,res in servers_res.items():
                        if res[0] == 200:
                            #found a good one, choose it
                            replacedservername = name
                            break
                        elif res[0] in OFFLINE_STATUSCODE_LIST:
                            continue
                        elif not replacedservername:
                            #fond a available one, but has some issues,choose it if can't find a good one
                            replacedservername = name

                    logger.debug("Replaced {1} with {2} for workload({0})".format(workloadname,servername,replacedservername))
                    if replacedservername:
                        datas[replacedservername] = servers_res[replacedservername]
                        del servers_res[replacedservername]
                        assignedworkloads[workloadname] = replacedservername
                        assignedworkloads_changed = True

                    if servers_res:
                        reassign_workloads -= 1
                    else:
                        reassign_workloads = 0
                    if reassign_workloads == 0:
                        break

            if assignedworkloads_changed:
                #save the workloads
                logger.debug("Save the changed running workloads data({}).".format(assignedworkloads))
                save_assignedworkloads(assignedworkloads)

        #map the healthdata result to workload. and remove status code
        result = OrderedDict()
        for workloadname in WORKLOADNAMES:
            servername = assignedworkloads.get(workloadname)
            if not servername:
                if settings.DEBUG:
                    result[workloadname] = "Can't find an available host for this non-assigned host.registered workloads: {0}, assigned workloads:{1}".format(str_workloads(workloads),assignedworkloads)
                else:
                    result[workloadname] = "Can't find an available host for this non-assigned host."
            elif servername not in datas:
                if settings.DEBUG:
                    result[workloadname] = "Can't find an available host for this assigned offline host({2}).registered workloads: {0}, assigned workloads:{1}".format(str_workloads(workloads),assignedworkloads,servername)
                else:
                    result[workloadname] = "Can't find an available host for this assigned offline host({0}).".format(servername)

            elif datas[servername][0] == 200:
                result[workloadname] = datas[servername][1]
                result[workloadname]["hostname"] = servername
            else:
                result[workloadname] = "{}: {}".format(servername,datas[servername][1])


        datas.clear()

        populate_summary_data(result)

        return JsonResponse(result)

elif WORKLOADS > 0 and not WORKLOAD_DEPLOYMENT:
    WORKLOADNAMES = [get_workloadname(index) for index in range(1,WORKLOADS + 1,1)]
    def healthdata_view(request):
        workloads,servers_res = harvest_healthdata(request)

        result = OrderedDict()
        for servername in WORKLOADNAMES:
            if result in servers_res:
                result[servername] = servers_res[servername][1]
            else:
                result[servername] = "Workload is offline.workloads={}".format(str_workloads(workloads))

        populate_summary_data(result)

        return JsonResponse(result)
elif WORKLOAD_DEPLOYMENT:
    def healthdata_view(request):
        workloads,servers_res = harvest_healthdata(request)

        result = OrderedDict()
        for servername, serverdata in servers_res.items():
            if serverdata[0] in OFFLINE_STATUSCODE_LIST:
                continue
            result[servername] = serverdata[1]

        populate_summary_data(result)

        return JsonResponse(result)
else:
    def healthdata_view(request):
        workloads,servers_res = harvest_healthdata(request)

        #get all workload names
        workloadnames = [k for k in workloads.keys() if k != item_version ]

        #find the name of the last available workload
        workloadnames.sort(key=lambda d:int(d[8:]))
        last_workloadname = next((name for name in reversed(workloadnames) if servers_res.get(name,[503,"Workload is Offline"])[0] not in OFFLINE_STATUSCODE_LSIT ) ,None)

        result = OrderedDict()
        if last_workloadname:
            #find the index of the last available workload
            last_workloadindex = int(last_workloadname[8:])

            #Return the healthdata of the workloads whose index is from 0 to last_workloadindex(include)
            for i in range(last_workloadindex + 1):
                servername = get_workloadname(i)
                serverdata = servers_res.get(servername,[503,"Workload is offline"])
                result[servername] = serverdata[1]

        populate_summary_data(result)

        return JsonResponse(result)


def workload_healthdata_view(request):
    global secret
    try:
        token = get_auth_bearer(request)
        if not token:
            return JsonResponse({"status":401,"message":"Missing access token."},status=599)
    
        if not secret or secret != token:
            workloads = cache.get(key_workloads)
            data = workloads.get(registerhostname)
            if data:
                secret = data[1]
            
            if secret != token:
                return JsonResponse({"status":401,"message":"Access token doesn't match."},status=599)
    
        statuscode,data = get_workload_healthdata()
        if statuscode == 200:
            return JsonResponse(data)
        else:
            return JsonResponse({"status":statuscode,"message":data},status=599)
    except Exception as ex:
        return JsonResponse({"status":500,"message":"{}:{}".format(ex.__class__.__name__,str(ex))},status=599)

def register_healtcheckurls():
    #Add urls
    rootconf_module = importlib.import_module(settings.ROOT_URLCONF)
    if not rootconf_module:
        raise Exception("Failed to load module '{}'".format(settings.ROOT_URLCONF))
    
    if HEALTHCHECK_ENABLED:
        urlpatterns = [
                path('healthcheck/healthdata', healthdata_view,name="healthdata"),
                path('workload/healthcheck/healthdata',workload_healthdata_view,name="workload_healthdata")
        ]
    else:
        urlpatterns = []

    rootconf_module.urlpatterns.append(path('',include((urlpatterns,'healthcheck'),namespace="healthcheck")))


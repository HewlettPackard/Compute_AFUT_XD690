# -*- coding: utf-8 -*-
# Copyright (c) 2022-2023 Hewlett Packard Enterprise, Inc. All rights reserved.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
import os
__metaclass__ = type
import json
import subprocess
import time
import uuid
from datetime import datetime
# Use a minimal local Redfish client to avoid collection import issues
from ansible.module_utils.urls import open_url
from ansible.module_utils.six.moves.urllib.error import URLError, HTTPError


def _encode_multipart_formdata(fields):
    """
    Self-contained multipart/form-data encoder used instead of
    requests_toolbelt.MultipartEncoder, whose old apt-packaged builds
    break on newer urllib3 (urllib3.contrib.appengine was removed in 2.x).
    fields: ordered dict of name -> (filename_or_None, value_or_fileobj, content_type)
    Returns: (body_bytes, content_type_header)
    """
    boundary = uuid.uuid4().hex
    parts = []
    for name, (filename, value, content_type) in fields.items():
        parts.append(b'--' + boundary.encode('ascii'))
        if filename:
            disposition = 'Content-Disposition: form-data; name="%s"; filename="%s"' % (name, os.path.basename(str(filename)))
        else:
            disposition = 'Content-Disposition: form-data; name="%s"' % name
        parts.append(disposition.encode('utf-8'))
        if content_type:
            parts.append(('Content-Type: %s' % content_type).encode('utf-8'))
        parts.append(b'')
        if hasattr(value, 'read'):
            data = value.read()
        elif isinstance(value, bytes):
            data = value
        else:
            data = str(value).encode('utf-8')
        parts.append(data)
    parts.append(b'--' + boundary.encode('ascii') + b'--')
    parts.append(b'')
    body = b'\r\n'.join(parts)
    return body, 'multipart/form-data; boundary=%s' % boundary
class RedfishUtils(object):
    def __init__(self, creds, root_uri, timeout, module, data_modification=False):
        self.creds = creds or {}
        self.root_uri = (root_uri or '').rstrip('/')
        self.timeout = timeout or 600
        self.module = module
        self.data_modification = data_modification

    def _auth_params(self, headers=None):
        username = self.creds.get('user')
        password = self.creds.get('pswd')
        token = self.creds.get('token')
        basic_auth = True
        if token:
            if headers is not None:
                headers['X-Auth-Token'] = token
            basic_auth = False
        return username, password, basic_auth

    def _request(self, method, url, data=None, headers=None, timeout=None):
        headers = headers or {'Accept': 'application/json'}
        username, password, basic_auth = self._auth_params(headers)
        try:
            payload = json.dumps(data) if isinstance(data, dict) else data
            resp = open_url(url, method=method, data=payload, headers=headers,
                            url_username=username, url_password=password,
                            force_basic_auth=basic_auth, validate_certs=False,
                            follow_redirects='all', use_proxy=True,
                            timeout=timeout or self.timeout)
            # Try to parse JSON body
            try:
                body = resp.read()
                if isinstance(body, bytes):
                    body = body.decode('utf-8', errors='ignore')
                body_str = body.strip() if isinstance(body, str) else ''
                parsed = json.loads(body_str) if body_str else {}
            except Exception:
                parsed = {}
            return {'ret': True, 'status': getattr(resp, 'code', None), 'data': parsed}
        except HTTPError as e:
            return {'ret': False, 'status': getattr(e, 'code', None), 'msg': 'HTTPError: %s' % e}
        except URLError as e:
            return {'ret': False, 'status': None, 'msg': 'URLError: %s' % e}
        except Exception as e:
            return {'ret': False, 'status': None, 'msg': str(e)}

    def get_request(self, url, headers=None, timeout=None):
        return self._request('GET', url, None, headers, timeout=timeout)

    def post_request(self, url, payload=None, headers=None):
        headers = headers or {'Content-Type': 'application/json'}
        return self._request('POST', url, payload, headers)

    def patch_request(self, url, payload=None, headers=None):
        headers = headers or {'Content-Type': 'application/json'}
        return self._request('PATCH', url, payload, headers)
from ansible.module_utils.urls import open_url, prepare_multipart
from ansible.module_utils.six.moves.urllib.error import URLError, HTTPError
import configparser

supported_models=["XD690", "NA"]

#to get inventory, update
partial_models={}

supported_targets={
    "NA": ["BMC", "CPLDBACK_0", "CPLDDCSM_0", "CPLDE1SBP_0", "CPLDMB_0", "PCIeSwitch_0",  "PCIeSwitch_1"],
}

# System firmware targets (non-GPU/HGX components) - based on actual Redfish inventory
XD690_targets = ['BMC', 'CPLDBACK_0', 'CPLDDCSM_0', 'CPLDE1SBP_0', 'CPLDMB_0', 
                 'PCIeSwitch_0', 'PCIeSwitch_1', 
                 'PSU_0', 'PSU_1', 'PSU_2', 'PSU_3', 'PSU_4', 'PSU_5', 
                 'PSU_6', 'PSU_7', 'PSU_8', 'PSU_9', 'PSU_10', 'PSU_11']

# GPU and HGX-related firmware targets - based on actual Redfish inventory
GPU_targets = ['HGX_FW_BMC_0', 
               'HGX_FW_ConnectX_0', 'HGX_FW_ConnectX_1', 'HGX_FW_ConnectX_2', 'HGX_FW_ConnectX_3',
               'HGX_FW_ConnectX_4', 'HGX_FW_ConnectX_5', 'HGX_FW_ConnectX_6',
               'HGX_FW_ConnectX_SMA_0', 'HGX_FW_ConnectX_SMA_1', 'HGX_FW_ConnectX_SMA_2', 'HGX_FW_ConnectX_SMA_3',
               'HGX_FW_ERoT_BMC_0', 'HGX_FW_ERoT_FPGA_0', 'HGX_FW_ERoT_NVLinkManagementNIC_0',
               'HGX_FW_ERoT_NVSwitch_0', 'HGX_FW_ERoT_NVSwitch_1',
               'HGX_FW_FPGA_0',
               'HGX_FW_GPU_0', 'HGX_FW_GPU_1', 'HGX_FW_GPU_2', 'HGX_FW_GPU_3',
               'HGX_FW_GPU_4', 'HGX_FW_GPU_5', 'HGX_FW_GPU_6', 'HGX_FW_GPU_7',
               'HGX_FW_NVLinkManagementNIC_0',
               'HGX_FW_NVSwitch_0', 'HGX_FW_NVSwitch_1',
               'HGX_FW_SXM_SMA_0', 'HGX_FW_SXM_SMA_1', 'HGX_FW_SXM_SMA_2', 'HGX_FW_SXM_SMA_3',
               'HGX_FW_SXM_SMA_4', 'HGX_FW_SXM_SMA_5', 'HGX_FW_SXM_SMA_6', 'HGX_FW_SXM_SMA_7',
               'HGX_InfoROM_GPU_0', 'HGX_InfoROM_GPU_1', 'HGX_InfoROM_GPU_2', 'HGX_InfoROM_GPU_3',
               'HGX_InfoROM_GPU_4', 'HGX_InfoROM_GPU_5', 'HGX_InfoROM_GPU_6', 'HGX_InfoROM_GPU_7']

reboot = {
    "BIOS": ["AC_PC_redfish"],
    "BIOS2": ["AC_PC_redfish"],
    "CPLDBACK_0": ["AC_cycle_ipmi"],
    "CPLDDCSM_0": ["AC_cycle_ipmi"],
    "CPLDE1SBP_0": ["AC_cycle_ipmi"],
    "CPLDMB_0": ["AC_cycle_ipmi"],
}

# CPLD component IDs that require IPMI AC cycle after update
CPLD_TARGETS = ('CPLDBACK_0', 'CPLDDCSM_0', 'CPLDE1SBP_0', 'CPLDMB_0')

routing = {
    "NA" : "",
}

class CrayRedfishUtils(RedfishUtils):
    def _normalize_redfish_uri(self, uri):
        if not uri:
            return None
        uri = str(uri).strip()
        if not uri:
            return None
        # Some implementations may return an absolute URL; store the path.
        if uri.startswith('http://') or uri.startswith('https://'):
            try:
                parts = uri.split('://', 1)[1].split('/', 1)
                uri = '/' + parts[1] if len(parts) > 1 else '/'
            except Exception:
                return uri
        if not uri.startswith('/'):
            uri = '/' + uri
        return uri

    def _task_id_key(self, task_uri):
        """Sort key for task URIs; prefers numeric suffix if present."""
        try:
            tail = str(task_uri).rstrip('/').split('/')[-1]
            return (0, int(tail))
        except Exception:
            return (1, str(task_uri))

    def _pick_latest_task_uri(self, task_uris):
        if not task_uris:
            return None
        try:
            return sorted(set(task_uris), key=self._task_id_key)[-1]
        except Exception:
            return list(task_uris)[-1]

    def list_task_uris(self):
        """Return list of task member URIs (paths) from TaskCollection."""
        resp = self.get_request(self.root_uri + "/redfish/v1/TaskService/Tasks")
        if resp.get('ret') is False:
            return []
        data = resp.get('data') or {}
        uris = []
        for member in (data.get('Members') or []):
            if not isinstance(member, dict):
                continue
            odata_id = member.get('@odata.id')
            if odata_id:
                norm = self._normalize_redfish_uri(odata_id)
                if norm:
                    uris.append(norm)
        return uris

    def _extract_task_uri_from_post_result(self, post_result):
        """Try to extract task URI from POST response headers/body."""
        if not post_result or not isinstance(post_result, dict):
            return None

        headers = (post_result.get('headers') or {})
        if isinstance(headers, dict):
            # Common patterns: Location / Content-Location / Link
            for k in ('location', 'content-location'):
                if headers.get(k):
                    return self._normalize_redfish_uri(headers.get(k))
            link_val = headers.get('link')
            if link_val:
                # e.g. <.../TaskService/Tasks/1>; rel=monitor
                try:
                    s = str(link_val)
                    if '<' in s and '>' in s:
                        between = s.split('<', 1)[1].split('>', 1)[0]
                        norm = self._normalize_redfish_uri(between)
                        if norm:
                            return norm
                except Exception:
                    pass

        body = post_result.get('data') or {}
        if isinstance(body, dict):
            for k in ('@odata.id', 'TaskMonitor', 'taskMonitor', 'task_monitor'):
                if body.get(k):
                    return self._normalize_redfish_uri(body.get(k))
            # Some implementations nest it
            oem = body.get('Oem')
            if isinstance(oem, dict):
                for v in oem.values():
                    if isinstance(v, dict):
                        if v.get('TaskMonitor'):
                            return self._normalize_redfish_uri(v.get('TaskMonitor'))
                        if v.get('@odata.id'):
                            return self._normalize_redfish_uri(v.get('@odata.id'))

        return None

    def resolve_latest_or_new_task_uri(self, post_result=None, tasks_before=None, settle_seconds=2):
        """Resolve the task created by this operation.

        Preference order:
        1) Task URI returned by POST (Location / TaskMonitor / @odata.id)
        2) If we have a before-snapshot, diff TaskCollection after POST and pick newest in the diff
        3) Otherwise pick the latest task by numeric id
        """
        task_uri = self._extract_task_uri_from_post_result(post_result)
        if task_uri:
            return task_uri

        before = [self._normalize_redfish_uri(u) for u in (tasks_before or [])]
        before_set = set([u for u in before if u])

        # Give BMC a moment to register the new task
        try:
            if settle_seconds and settle_seconds > 0:
                time.sleep(settle_seconds)
        except Exception:
            pass

        after = self.list_task_uris()
        if before_set:
            created = list(set(after) - before_set)
            if created:
                return self._pick_latest_task_uri(created)
        return self._pick_latest_task_uri(after)

    def ensure_update_service_ready(self, max_wait_seconds=120):
        """Ensure UpdateService is enabled and not busy before firmware update."""
        deadline = time.time() + max_wait_seconds
        last = None
        
        while time.time() < deadline:
            resp = self.get_request(self.root_uri + "/redfish/v1/UpdateService")
            last = resp
            if resp.get('ret') is False:
                return {'ret': False, 'msg': resp.get('msg', 'UpdateService api not found')}

            data = resp.get('data') or {}
            if data.get('ServiceEnabled') is not True:
                return {'ret': False, 'msg': 'UpdateService.ServiceEnabled is false'}

            state = ((data.get('Status') or {}).get('State'))
            if state and str(state).lower() != 'enabled':
                return {'ret': False, 'msg': 'UpdateService.Status.State is not Enabled: %s' % state}

            # Wait if UpdateService is busy
            if data.get('HttpPushUriOptionsBusy') or data.get('HttpPushUriTargetsBusy'):
                time.sleep(5)
                continue

            return {'ret': True, 'data': data}

        return {'ret': False, 'msg': 'Timed out waiting for UpdateService to be ready', 'last': last}
    def post_multi_request(self, uri, headers, payload):
        username, password, basic_auth = self._auth_params(headers)
        try:
            resp = open_url(uri, data=payload, headers=headers, method="POST",
                            url_username=username, url_password=password,
                            force_basic_auth=basic_auth, validate_certs=False,
                            follow_redirects='all',
                            use_proxy=True, timeout=self.timeout)
            resp_headers = dict((k.lower(), v) for (k, v) in resp.info().items())

            # Best-effort parse response body (may be empty on 202/204)
            parsed = {}
            try:
                body = resp.read()
                if isinstance(body, bytes):
                    body = body.decode('utf-8', errors='ignore')
                body_str = body.strip() if isinstance(body, str) else ''
                parsed = json.loads(body_str) if body_str else {}
            except Exception:
                parsed = {}

            return {
                'ret': True,
                'status': getattr(resp, 'code', None),
                'headers': resp_headers,
                'data': parsed,
            }
        except HTTPError as e:
            return {'ret': False, 'status': getattr(e, 'code', None), 'msg': 'HTTPError: %s' % e}
        except URLError as e:
            return {'ret': False, 'status': None, 'msg': 'URLError: %s' % e}
        except Exception as e:
            return {'ret': False, 'status': None, 'msg': str(e)}

    def get_model(self):
        # Fast model lookup only (keeps requests low to avoid slowness).
        # Some platforms may not expose Model here; in that case we return "NA".
        model = "NA"
        for system_uri in (
            "/redfish/v1/Systems/DGX",
            "/redfish/v1/Systems/HGX_Baseboard_0",
            "/redfish/v1/Systems/Self"
        ):
            try:
                response = self.get_request(self.root_uri + system_uri)
                if not response.get('ret'):
                    continue
                data = response.get('data') or {}
                model_val = data.get('Model')
                if model_val:
                    model = str(model_val).strip()
                    if model != "NA":
                        # Remember which URI actually resolves on this BMC - some
                        # platforms don't expose a 'Self' alias, so power actions
                        # elsewhere shouldn't hardcode it.
                        self._system_uri = system_uri
                        break
            except Exception:
                continue

        if model == "NA":
            return "NA"

        if model not in partial_models and "XD" in model:
            split_model_array = model.split() #["HPE", "Cray", "XD665"]
            for dum in split_model_array:
                if "XD" in dum:
                    partial_models[model.upper()]=dum.upper()
        return model

    def _system_resource_uri(self):
        """Return the /redfish/v1/Systems/<id> path that actually resolves on
        this BMC, discovering it via get_model() if not already cached.
        """
        if not getattr(self, '_system_uri', None):
            self.get_model()
        return getattr(self, '_system_uri', None) or "/redfish/v1/Systems/Self"

    def get_firmware_inventory_collection(self):
        """Return FirmwareInventory as a dict of {Name: Version}.

        Matches the curl output you provided, which includes
        Oem.Ami.FirmwareInventory entries with Name+Version.
        """
        resp = self.get_request(self.root_uri + "/redfish/v1/UpdateService/FirmwareInventory")
        if resp.get('ret') is False:
            return {'ret': False, 'msg': resp.get('msg', 'Failed to fetch FirmwareInventory')}

        data = resp.get('data') or {}
        inventory = {}

        # Preferred: AMI OEM list with Name/Version pairs
        try:
            oem_list = data.get('Oem', {}).get('Ami', {}).get('FirmwareInventory', [])
            for item in oem_list:
                if not isinstance(item, dict):
                    continue
                name = item.get('Name')
                version = item.get('Version')
                if name:
                    inventory[str(name)] = str(version) if version is not None else "NA"
        except Exception:
            pass

        # Fallback: query each member for its Version
        if not inventory:
            try:
                for member in data.get('Members', []) or []:
                    if not isinstance(member, dict):
                        continue
                    odata_id = member.get('@odata.id')
                    if not odata_id:
                        continue
                    target = str(odata_id).rstrip('/').split('/')[-1]
                    inventory[target] = self.get_fw_version(target)
            except Exception:
                pass

        return {'ret': True, 'inventory': inventory}

    def power_state(self):
        response = self.get_request(self.root_uri + self._system_resource_uri())
        if response['ret'] is False:
            return "NA"
        state='None'
        try:
            if 'PowerState' in response['data']:
                state = response['data'][u'PowerState'].strip()
        except:
            if 'PowerState' in response:
                state = response[u'PowerState'].strip()
        return state

    def power_on(self):
        payload = {"ResetType": "On"}
        target_uri = self._system_resource_uri() + "/Actions/ComputerSystem.Reset"
        response1 = self.post_request(self.root_uri + target_uri, payload)
        time.sleep(120)

    def power_off(self):
        payload = {"ResetType": "ForceOff"}
        target_uri = self._system_resource_uri() + "/Actions/ComputerSystem.Reset"
        response1 = self.post_request(self.root_uri + target_uri, payload)
        time.sleep(120)

    def get_PS_CrayXD690(self,attr):
        ini_path = os.path.join(os.getcwd(),'config.ini')
        config = configparser.ConfigParser()
        IP = attr.get('baseuri')
        username = attr.get('username')
        password = attr.get('password')
        config.read(ini_path)
        try:
            option = config.get('Options','power_state')
            if option=="":
                return {'ret': False, 'changed': True, 'msg': 'Must specify the required option for power_state in config.ini'}
        except:
            return {'ret': False, 'changed': True, 'msg': 'Must specify the required option for power_state in config.ini'}

        csv_file_name = attr.get('output_file_name')
        if not os.path.exists(csv_file_name):
            f = open(csv_file_name, "w")
            to_write="IP_Address,Model,Power_State\n"
            f.write(to_write)
            f.close()
        model = self.get_model()
        if "XD690" in model.upper():
            power_state = self.power_state()
            if option.upper()=="NA":
                lis=[IP,model,power_state]
            elif option.upper()=="ON":
                if power_state.upper()=="OFF":
                    self.power_on()
                power_state = self.power_state()
                lis=[IP,model,power_state]
            elif option.upper()=="OFF":
                if power_state.upper()=="ON":
                    self.power_off()
                power_state = self.power_state()
                lis=[IP,model,power_state]
            elif option.upper()=="REBOOT":
                # Redfish graceful reboot - same action used after a BIOS/CPLD update
                self.AC_PC_redfish()
                power_state = self.power_state()
                lis=[IP,model,power_state]
            elif option.upper() in ("AC_CYCLE", "AC_CYCLE_IPMI"):
                # IPMI AC power cycle (raw 0x3c 0x99) - same action used after a CPLD update
                if not username or not password:
                    return {'ret': False, 'changed': True, 'msg': 'username/password are required for AC_CYCLE'}
                cycled, cycle_msg = self.ac_cycle_ipmi(IP, username, password)
                if not cycled:
                    return {'ret': False, 'changed': True, 'msg': 'ac_cycle failed: %s' % cycle_msg}
                # An AC cycle isn't instant - give the system time to actually
                # power down/up again before reporting a (likely stale) state.
                time.sleep(180)
                power_state = self.power_state()
                lis=[IP,model,power_state]
            else:
                return {'ret': False, 'changed': True, 'msg': 'Must specify the correct required option for power_state in config.ini'}

        else:
            lis=[IP,model,"unsupported_model"]
        new_data=",".join(lis)
        return {'ret': True,'changed': True, 'msg': str(new_data)}

    def target_supported(self,model,target,image_type):
        try:
            if 'HMC' in image_type:
                return True
            if 'RCU' in image_type:
                return True
            elif target in supported_targets[partial_models[model.upper()]]:
                return True
            return False
        except:
            return False

    def get_fw_version(self, target):
        """
        Get firmware version for a specific target.
        Returns: Version string or "NA" if not found.
        """
        try:
            response = self.get_request(self.root_uri + "/redfish/v1/UpdateService/FirmwareInventory" + "/" + target)
            if response['ret'] is False:
                return "NA"
            try:
                version = response['data']['Version']
                return version
            except:
                version = response['Version']
                return version
        except:
            return "NA"

    def write_json_result(self, json_file_name, result_data):
        """
        Helper function to write results to JSON file.
        Maintains a list of results and includes summary information.
        """
        # Initialize or read existing data
        if os.path.exists(json_file_name):
            try:
                with open(json_file_name, 'r') as f:
                    data = json.load(f)
            except:
                data = {"summary": {}, "results": []}
        else:
            data = {"summary": {}, "results": []}
        
        # Add new result
        data["results"].append(result_data)
        
        # Update summary
        data["summary"]["total_systems"] = len(data["results"])
        data["summary"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Count statuses
        status_counts = {}
        for result in data["results"]:
            status = result.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        data["summary"]["status_counts"] = status_counts
        
        # Write to file with pretty formatting
        with open(json_file_name, 'w') as f:
            json.dump(data, f, indent=2)

    def bmcfreememory(self):
        payload = {}
        target_uri = "/redfish/v1/UpdateService/Action/Oem/Gbt/HMCUpdate.PrepareFreeMemory"
        response = self.post_request(self.root_uri + target_uri, payload)
        return response

    def AC_PC_redfish(self):
        payload = {"ResetType": "ForceRestart"}
        target_uri = self._system_resource_uri() + "/Actions/ComputerSystem.Reset"
        response1 = self.post_request(self.root_uri + target_uri, payload)
        time.sleep(180)
        target_uri = "/redfish/v1/Chassis/Self/Actions/Chassis.Reset"
        response2 = self.post_request(self.root_uri + target_uri, payload)
        time.sleep(180)
        return response1 or response2

    def AC_PC_ipmi(self, IP, username, password, routing_value):
        try:
            command='ipmitool -I lanplus -H '+IP+' -U '+username+' -P '+password+' raw '+ routing_value
            subprocess.run(command, shell=True, check=True, timeout=15)
            time.sleep(300)
            self.power_on()
            return True
        except:
            return False

    def ac_cycle_ipmi(self, IP, username, password):
        """Perform AC power cycle via IPMI raw command 0x3c 0x99.
        Used after CPLD firmware updates to activate the new firmware.
        Returns: (success, message) - message carries ipmitool's own
        output/error so callers aren't left guessing why it failed.
        """
        command = 'ipmitool -I lanplus -H %s -U %s -P %s raw 0x3c 0x99' % (IP, username, password)
        try:
            result = subprocess.run(command, shell=True, timeout=30, capture_output=True, text=True)
            output = (result.stdout or '').strip() or (result.stderr or '').strip()
            if result.returncode == 0:
                return True, output or "AC cycle command accepted"
            return False, "ipmitool exited %s: %s" % (result.returncode, output or "no output")
        except Exception as e:
            return False, str(e)

    def get_gpu_inventory(self, attr):
        """
        Get GPU firmware inventory for all GPU-related targets.
        Results are written to JSON file.
        """
        IP = attr.get('baseuri')
        json_file_name = attr.get('output_file_name')
        model = self.get_model()
        
        # Prepare result data structure
        result_data = {
            "ip_address": IP,
            "model": model,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "gpu_firmware_versions": {}
        }
        
        inv_resp = self.get_firmware_inventory_collection()
        if inv_resp.get('ret') is False:
            result_data["status"] = "inventory_fetch_failed"
            result_data["message"] = inv_resp.get('msg', 'Failed to fetch FirmwareInventory')
        else:
            inventory = inv_resp.get('inventory', {})
            hgx_items = {k: v for (k, v) in inventory.items() if str(k).upper().startswith('HGX_')}
            result_data["status"] = "success" if hgx_items else "no_hgx_entries"
            result_data["gpu_firmware_versions"].update(hgx_items)
        
        # Write to JSON file
        self.write_json_result(json_file_name, result_data)
        
        return {'ret': True, 'changed': True, 'msg': json.dumps(result_data)}

    def get_sys_fw_inventory(self, attr):
        """
        Get system firmware inventory for BMC and other targets.
        Results are written to JSON file.
        """
        IP = attr.get('baseuri')
        json_file_name = attr.get('output_file_name')
        model = self.get_model()
        
        # Prepare result data structure
        result_data = {
            "ip_address": IP,
            "model": model,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "firmware_versions": {}
        }
        
        inv_resp = self.get_firmware_inventory_collection()
        if inv_resp.get('ret') is False:
            result_data["status"] = "inventory_fetch_failed"
            result_data["message"] = inv_resp.get('msg', 'Failed to fetch FirmwareInventory')
        else:
            inventory = inv_resp.get('inventory', {})
            sys_items = {k: v for (k, v) in inventory.items() if not str(k).upper().startswith('HGX_')}
            result_data["status"] = "success" if sys_items else "no_system_entries"
            result_data["firmware_versions"].update(sys_items)
        
        # Write to JSON file
        self.write_json_result(json_file_name, result_data)
        
        return {'ret': True, 'changed': True, 'msg': json.dumps(result_data)}

    def _detect_image_type(self, image_path):
        """
        Detect the firmware image type based on file extension.
        Returns: tuple (image_type, is_pldm_bundle)
        - For .fwpkg files: (None, True) - PLDM bundle, no ImageType needed
        - For .hpm files: ('HPM', False)
        - For other files: (None, False) - let BMC auto-detect
        """
        if not image_path:
            return (None, False)
        
        lower_path = image_path.lower()
        if lower_path.endswith('.fwpkg'):
            return (None, True)  # PLDM bundle format
        elif lower_path.endswith('.hpm'):
            return ('HPM', False)
        else:
            return (None, False)  # Auto-detect

    def _is_task_completed(self, data):
        """Check if task data indicates completion (success or failure).
        Returns: (is_done, is_success) tuple. is_done is True for a confirmed
        terminal state, or the string 'provisional' for a 100%/OK signal that
        isn't backed by an explicit terminal TaskState yet - some BMCs report
        this transiently before later flipping to Exception during final
        validation, so callers should re-confirm before trusting it.
        """
        task_state = data.get('TaskState', '')
        task_status = data.get('TaskStatus', '')
        percent = data.get('PercentComplete', 0)
        messages = data.get('Messages', [])

        # Explicit completion states
        if task_state == 'Completed':
            return (True, True)
        if task_state in ('Exception', 'Killed', 'Cancelled'):
            return (True, False)

        # Check messages for completion indicators
        for msg in (messages or []):
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get('MessageId', '')
            if 'Task.1.0.Completed' in msg_id or 'UpdateSuccessful' in msg_id:
                return (True, True)
            if 'FirmwareUpdateCompleted' in msg_id:
                return (True, True)

        # 100% with OK status, but no explicit terminal TaskState - provisional only
        if percent == 100 and task_status == 'OK':
            return ('provisional', True)

        return (False, False)

    def _poll_task_completion(self, task_uri, timeout_seconds=1800, poll_interval=10):
        """
        Poll a task URI until completion or timeout.
        Uses a short HTTP timeout (30s) per request to avoid blocking the entire
        deadline on a single hung request.
        Returns: dict with 'ret', 'state', 'status', 'messages', 'progress_log'
        """
        if not task_uri:
            return {'ret': False, 'msg': 'No task URI provided'}

        POLL_HTTP_TIMEOUT = 30  # Short timeout per GET to avoid blocking
        deadline = time.time() + timeout_seconds
        start_time = time.time()
        last_percent = -1
        last_state = None
        progress_log = []

        def _build_result(data, success):
            return {
                'ret': success,
                'state': data.get('TaskState', ''),
                'status': data.get('TaskStatus', ''),
                'percent': data.get('PercentComplete', 0),
                'messages': data.get('Messages', []),
                'data': data,
                'progress_log': progress_log
            }

        while time.time() < deadline:
            resp = self.get_request(self.root_uri + task_uri, timeout=POLL_HTTP_TIMEOUT)
            if resp.get('ret') is False:
                time.sleep(poll_interval)
                continue

            data = resp.get('data') or {}
            task_state = data.get('TaskState', '')
            percent = data.get('PercentComplete', 0)

            # Log progress changes
            if percent != last_percent or task_state != last_state:
                elapsed = int(time.time() - start_time)
                progress_log.append({
                    'elapsed_seconds': elapsed,
                    'state': task_state,
                    'percent': percent,
                    'status': data.get('TaskStatus', '')
                })
                last_percent = percent
                last_state = task_state

            is_done, is_success = self._is_task_completed(data)
            if is_done is True:
                return _build_result(data, is_success)
            if is_done == 'provisional':
                # Don't trust a bare 100%/OK signal immediately - give the BMC
                # a moment to flip to Exception during final validation if
                # it's going to, then re-check before declaring success.
                time.sleep(20)
                confirm_resp = self.get_request(self.root_uri + task_uri, timeout=POLL_HTTP_TIMEOUT)
                if confirm_resp.get('ret'):
                    confirm_data = confirm_resp.get('data') or {}
                    confirm_done, confirm_success = self._is_task_completed(confirm_data)
                    if confirm_done is True:
                        return _build_result(confirm_data, confirm_success)
                    if confirm_done == 'provisional':
                        # Still just 100%/OK after the grace period - accept it.
                        return _build_result(confirm_data, True)
                # Confirmation request failed - keep polling normally.

            time.sleep(poll_interval)

        # Timeout reached — do one final check (task may have completed during last sleep)
        resp = self.get_request(self.root_uri + task_uri, timeout=POLL_HTTP_TIMEOUT)
        if resp.get('ret'):
            data = resp.get('data') or {}
            is_done, is_success = self._is_task_completed(data)
            if is_done:
                return _build_result(data, is_success)

        return {'ret': False, 'msg': 'Task polling timed out', 'state': last_state, 'percent': last_percent, 'progress_log': progress_log}

    def fetch_update_target_XD690(self, timeout_seconds=300, poll_interval=15):
            """
            Fetch the appropriate update target for XD690 systems.
            Polls the task until the 'Update.1.0.TargetDetermined' message
            appears or the task reaches a terminal state - a single
            fixed-delay check missed this message on slower transfers.
            Returns: update_target string or None
            """
            if not self._last_task_uri:
                return None

            target_uri = self._last_task_uri
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                try:
                    resp = self.get_request(self.root_uri + target_uri)
                    if resp.get('ret') is False:
                        return None

                    data = resp.get('data') or {}
                    messages = data.get('Messages') or []

                    for msg in messages:
                        if not isinstance(msg, dict):
                            continue

                        msg_id = msg.get('MessageId', '')
                        if msg_id == "Update.1.0.TargetDetermined":
                            msg_args = msg.get('MessageArgs', [])
                            if msg_args and len(msg_args) > 0:
                                return msg_args[0]

                    if data.get('TaskState') in ('Completed', 'Exception', 'Killed', 'Cancelled'):
                        return None
                except Exception:
                    return None

                time.sleep(poll_interval)

            return None
            
    def _resolve_canonical_target(self, raw_target, inventory):
        """Resolve the BMC task's free-text target name (e.g. 'HostBMC_0')
        to the actual FirmwareInventory member name (e.g. 'BMC') by matching
        against the live inventory collection fetched from the BMC itself.
        Avoids hardcoding any naming/folder convention that could change.
        """
        if not raw_target or not isinstance(inventory, dict):
            return raw_target

        # Exact match against a real inventory member name
        if raw_target in inventory:
            return raw_target

        raw_upper = raw_target.upper()
        for name in inventory.keys():
            name_upper = name.upper()
            if name_upper == raw_upper:
                return name
            # e.g. raw_target 'HostBMC_0' contains inventory name 'BMC',
            # or inventory name contains the raw target string
            if name_upper in raw_upper or raw_upper in name_upper:
                return name

        # No confident match found in the live inventory - fall back to
        # whatever the BMC's task message reported.
        return raw_target

    def helper_update(self, update_status, image_path, image_type, IP, username, password, model):
        """
        Generic helper function to update firmware.
        Uses /redfish/v1/UpdateService/upload endpoint with:
        - UpdateParameters: {"Targets":[],"ForceUpdate":true}
        - UpdateFile: firmware image (.fwpkg format)
        Returns: (before_version, after_version, update_status)
        """
        before_version = None
        after_version = None
        update_status = None

        # Ensure UpdateService is ready
        ready = self.ensure_update_service_ready()
        if ready.get('ret') is False:
            update_status = ready.get('msg', 'UpdateService not ready')
            after_version = "NA"
            return before_version, after_version, update_status

        # Use the documented endpoint: /redfish/v1/UpdateService/upload
        upload_uri = "/redfish/v1/UpdateService/upload"
        
        # Prepare multipart request for firmware update
        # Per documentation: UpdateParameters={"Targets":[],"ForceUpdate":true}
        headers = {'Expect': 'Continue', 'Content-Type': 'multipart/form-data'}
        body = {}
        
        # UpdateParameters with empty Targets array and ForceUpdate=true
        # This is the documented format for .fwpkg firmware updates
        update_params = {"Targets": [], "ForceUpdate": True}
        body['UpdateParameters'] = (None, json.dumps(update_params), 'application/json')

        # Snapshot firmware inventory before the upload starts. Querying a
        # target's version mid-task (after upload begins) is unreliable since
        # its FirmwareInventory record is often unavailable while transferring.
        # get_firmware_inventory_collection() returns {'ret':.., 'inventory': {name: version}} -
        # unwrap it here so lookups below are against the actual name->version map.
        pre_inventory_resp = self.get_firmware_inventory_collection()
        pre_inventory = pre_inventory_resp.get('inventory') or {} if pre_inventory_resp.get('ret') else {}

        with open(image_path, 'rb') as image_path_rb:
            body['UpdateFile'] = (os.path.basename(image_path), image_path_rb, 'application/octet-stream')
            encoded_body, content_type = _encode_multipart_formdata(body)
            headers['Content-Type'] = content_type
            tasks_before = self.list_task_uris()
            post_result = self.post_multi_request(self.root_uri + upload_uri,
                                        headers=headers, payload=encoded_body)
            if not post_result.get('ret'):
                update_status = "failed_Post: %s" % post_result.get('msg', 'unknown')
                after_version = "NA"
            else:
                self._last_task_uri = self.resolve_latest_or_new_task_uri(post_result=post_result, tasks_before=tasks_before)
                
                # Poll task for completion with live progress
                # Resolve the BMC's free-text target name against the live
                # FirmwareInventory collection fetched before the update.
                raw_target = self.fetch_update_target_XD690()
                self.target = self._resolve_canonical_target(raw_target, pre_inventory)
                if self.target:
                    before_version = pre_inventory.get(self.target, "NA")
                if self._last_task_uri:
                    # 60 min - some firmware images (e.g. CPLD) can genuinely
                    # still be "Running" past 30 min; a real timeout previously
                    # killed an in-progress-but-healthy task and stopped the
                    # whole ordered sequence.
                    task_result = self._poll_task_completion(self._last_task_uri, timeout_seconds=3600)
                    if task_result.get('ret'):
                        update_status = "success"
                    else:
                        # Extract error messages from task
                        messages = task_result.get('messages', [])
                        error_msgs = []
                        for msg in messages:
                            if isinstance(msg, dict):
                                error_msgs.append(msg.get('Message', str(msg)))
                        update_status = "Task failed: %s (State: %s)" % (
                            '; '.join(error_msgs) if error_msgs else task_result.get('msg', 'Unknown error'),
                            task_result.get('state', 'Unknown')
                        )
                else:
                    # No task URI - assume success if POST returned OK
                    update_status = "success"

                # Post-update actions per target type - only when the task
                # itself actually succeeded; on failure just report "NA" so a
                # failed step never gets a misleading "pending_final_*" marker
                # that never gets backfilled (the sequence stops on failure).
                target_name = (self.target or "").upper()
                if update_status != "success":
                    after_version = "NA"
                elif target_name == 'BMC':
                    # BMC reboots after update - wait 5 minutes for it to come back
                    time.sleep(300)
                    after_version = "NA"
                    for retry in range(6):
                        ver = self.get_fw_version(self.target)
                        if not ver.startswith("NA"):
                            after_version = ver
                            break
                        time.sleep(30)
                elif target_name in ('BIOS', 'BIOS2'):
                    # BIOS PLDM update: after task reaches 100%, BMC automatically
                    # performs DC cycle -> AC cycle -> flash recovery -> 2nd DC -> 2nd AC.
                    # Defer that wait + version check to the end of the whole ordered
                    # sequence instead of doing it per-step, so multiple firmware in
                    # one run only go through this settle-and-reboot once.
                    self._pending_reboot = True
                    after_version = "pending_final_reboot"
                elif target_name in CPLD_TARGETS:
                    # CPLD updates require an IPMI AC power cycle to activate.
                    # Defer the cycle + version check to the end of the whole
                    # ordered sequence instead of doing it per-step, so multiple
                    # CPLD entries in one run only get AC-cycled once.
                    self._pending_ac_cycle = True
                    after_version = "pending_final_ac_cycle"
                elif self.target and self.target in pre_inventory:
                    # Other single-component targets - get version immediately
                    after_version = self.get_fw_version(self.target)
                else:
                    # Multi-component bundle (e.g. a GPU/HGX package touching many
                    # FirmwareInventory entries at once) - the reported target
                    # doesn't map to any single real component, so there's no one
                    # version to look up. Instead, diff the whole inventory before
                    # vs after and report every component whose version changed.
                    before_version = {}
                    after_version = "NA"
                    for retry in range(6):
                        post_resp = self.get_firmware_inventory_collection()
                        post_inventory = post_resp.get('inventory') or {} if post_resp.get('ret') else {}
                        changed = {name: ver for name, ver in post_inventory.items()
                                   if pre_inventory.get(name, "NA") != ver}
                        if changed:
                            before_version = {name: pre_inventory.get(name, "NA") for name in changed}
                            after_version = changed
                            break
                        time.sleep(30)

        
        return before_version, after_version, update_status

    def _append_to_json_log(self, json_file_path, result_data):
        """
        Append a firmware update result to JSON log file.
        Creates the file if it doesn't exist, or appends to existing results.
        """
        # Initialize or load existing data
        if os.path.exists(json_file_path):
            try:
                with open(json_file_path, 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted or empty, start fresh
                data = {"update_summary": {}, "results": []}
        else:
            data = {
                "update_summary": {
                    "tool_name": "HPE Cray XD BMC Firmware Update Tool",
                    "start_time": datetime.utcnow().isoformat() + "Z",
                    "total_systems": 0,
                    "successful": 0,
                    "failed": 0
                },
                "results": []
            }
        
        # Add timestamp to result
        result_data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        # Append new result
        data["results"].append(result_data)
        
        # Update summary statistics
        data["update_summary"]["total_systems"] = len(data["results"])
        data["update_summary"]["last_update"] = datetime.utcnow().isoformat() + "Z"
        
        # Count successes and failures
        successful = sum(1 for r in data["results"] if r.get("status", "").lower() == "success")
        failed = len(data["results"]) - successful
        data["update_summary"]["successful"] = successful
        data["update_summary"]["failed"] = failed
        
        # Write updated data to file with pretty formatting
        with open(json_file_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        return True

    def get_firmware_order(self, config, model):
        """
        Build the ordered list of firmware image paths to flash in sequence.

        Looks for a model-specific section [Firmware_Order_XD690] first
        (keys are the flash order, e.g. 1, 2, 3, ...), falling back to the
        generic [Firmware_Order] section. For a single/individual firmware
        update, just list one entry in the section (e.g. only "1 = <path>").
        """
        short_model = partial_models.get(model.upper()) if model != "NA" else None
        section_candidates = []
        if short_model:
            section_candidates.append('Firmware_Order_%s' % short_model)
        section_candidates.append('Firmware_Order')

        for section in section_candidates:
            if config.has_section(section):
                items = config.items(section)
                try:
                    ordered_items = sorted(items, key=lambda kv: int(kv[0]))
                except ValueError:
                    ordered_items = items
                paths = [value.strip() for _, value in ordered_items if value and value.strip()]
                if paths:
                    return paths

        return []

    def system_fw_update(self, attr):
        """
        Main function to update one or more firmware images on a single target.
        Reads the ordered firmware list from config.ini and flashes each image
        one at a time, in the configured order, stopping the sequence on the
        first failure. Results for every step are logged to a JSON file.
        """
        ini_path = os.path.join(os.getcwd(), 'config.ini')
        config = configparser.ConfigParser()
        config.read(ini_path)
        self.target = ""

        IP = attr.get('baseuri')
        username = attr.get('username')
        password = attr.get('password')
        output_file_name = attr.get('output_file_name')

        # Convert to JSON if CSV extension provided
        if output_file_name.endswith('.csv'):
            output_file_name = output_file_name.replace('.csv', '.json')
        elif not output_file_name.endswith('.json'):
            output_file_name += '.json'

        # Image type will be auto-detected from file extension
        image_type = None

        # Get system model
        model = self.get_model()

        firmware_list = self.get_firmware_order(config, model)
        if not firmware_list:
            return {'ret': False, 'changed': True,
                     'msg': 'Must specify at least one entry in the '
                            '[Firmware_Order_XD690] (or [Firmware_Order]) section in config.ini'}

        total_steps = len(firmware_list)
        step_results = []
        all_succeeded = True
        self._pending_reboot = False
        self._pending_ac_cycle = False

        for step, image_path in enumerate(firmware_list, start=1):
            result_data = {
                "ip_address": IP,
                "model": model,
                "step": step,
                "total_steps": total_steps,
                "firmware_image": os.path.basename(image_path),
                "target": "",
                "fw_version_before": "NA",
                "fw_version_after": "NA",
                "status": "unknown",
                "message": "",
                "task_uri": ""
            }

            if not os.path.isfile(image_path):
                result_data["status"] = "firmware_file_not_found"
                result_data["message"] = f"[{step}/{total_steps}] Firmware file not found at: {image_path}"
                self._append_to_json_log(output_file_name, result_data)
                step_results.append(result_data)
                all_succeeded = False
                break

            # Perform firmware update for this step
            bef_ver, aft_ver, update_status = self.helper_update(None, image_path, image_type, IP, username, password, model)
            result_data["target"] = self.target
            result_data["fw_version_before"] = bef_ver
            result_data["fw_version_after"] = aft_ver
            result_data["status"] = update_status
            result_data["task_uri"] = getattr(self, '_last_task_uri', '') or ""

            if update_status and update_status.lower() == "success":
                result_data["message"] = f"[{step}/{total_steps}] {self.target} firmware successfully updated from {bef_ver} to {aft_ver}"
            else:
                result_data["message"] = f"[{step}/{total_steps}] {self.target} firmware update failed with status: {update_status}"

            self._append_to_json_log(output_file_name, result_data)
            step_results.append(result_data)

            if not update_status or update_status.lower() != "success":
                # Stop the ordered sequence on first failure; later firmware
                # in the list may depend on this one having succeeded.
                all_succeeded = False
                break

        # Perform the deferred BIOS reboot / CPLD AC-cycle once, at the end of
        # the whole ordered sequence, instead of once per BIOS/CPLD step.
        if all_succeeded and total_steps > 0:
            if self._pending_reboot:
                time.sleep(1800)  # 30 min for BMC's automatic power cycles to complete
            if self._pending_ac_cycle:
                time.sleep(120)  # let BMC settle after the last CPLD update
                self.ac_cycle_ipmi(IP, username, password)
                time.sleep(180)  # let the system recover after the AC cycle

            # Backfill fw_version_after for every step that deferred its check
            for result_data in step_results:
                if result_data.get("fw_version_after") not in ("pending_final_reboot", "pending_final_ac_cycle"):
                    continue
                target = result_data.get("target")
                final_version = "NA"
                for retry in range(10):
                    ver = self.get_fw_version(target)
                    if not ver.startswith("NA"):
                        final_version = ver
                        break
                    time.sleep(30)
                result_data["fw_version_after"] = final_version
                result_data["message"] = (
                    f"[{result_data['step']}/{total_steps}] {target} firmware successfully updated "
                    f"from {result_data.get('fw_version_before')} to {final_version}"
                )
                self._append_to_json_log(output_file_name, result_data)

        # Final host reboot once the whole ordered sequence has completed
        # successfully, so all flashed firmware takes effect.
        if all_succeeded and total_steps > 0:
            self.AC_PC_redfish()

        summary = {
            "ip_address": IP,
            "model": model,
            "total_steps": total_steps,
            "completed_steps": len(step_results),
            "overall_status": "success" if all_succeeded else "failed",
            "steps": step_results,
        }

        return {'ret': all_succeeded, 'changed': True, 'msg': json.dumps(summary)}
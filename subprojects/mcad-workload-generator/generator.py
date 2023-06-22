#! /usr/bin/env python3

import sys
import yaml
import pathlib
import jsonpath_ng
import copy
from collections import defaultdict

import k8s_quantity

"""
    number/type of nodes available,

    number of AppWrappers,

    number of Pod per AppWrappers,

    amount of memory/CPU per Pod,
    number of GPU per Pod

    duration of the Pod execution

"""

with open(pathlib.Path(__file__).parent / "base_appwrapper.yaml") as f:
    base_appwrapper = yaml.safe_load(f)

with open(pathlib.Path(__file__).parent / "config.yaml") as f:
    main_config = yaml.safe_load(f)

def get_config(jsonpath, config=main_config):
    return jsonpath_ng.parse(jsonpath).find(config)[0].value

def set_config(config, jsonpath, value):
    get_config(jsonpath, config=config) # will raise an exception if the jsonpath does not exist
    jsonpath_ng.parse(jsonpath).update(config, value)

def main():
    base_name = get_config("base_name")
    namespace = get_config("namespace")

    set_config(base_appwrapper, "metadata.name", base_name)
    set_config(base_appwrapper, "metadata.namespace", namespace)
    set_config(base_appwrapper, "spec.priority", get_config("defaults.priority"))

    job_template = get_config("job_template")

    summary = []
    total_aw_count = 0
    total_aws_configs = len(get_config("aw_resources"))
    for aw_index, aw_resource in enumerate(get_config("aw_resources")):
        aw_count = get_config("count", aw_resource)
        aw_pod_count = get_config("pods", aw_resource)
        aw_pod_runtime = get_config("runtime", aw_resource)
        aw_pod_resources = get_config("resources", aw_resource)

        all_aw_total_resources = {}
        aw_total_resources = {}
        summary_aw = []
        summary_all_aw = []

        total_aw_count += aw_count

        for res_name, res_quantity in aw_pod_resources.items():
            aw_total = float(k8s_quantity.parse_quantity(res_quantity)) * aw_pod_count
            aw_total_resources[res_name] = aw_total
            all_aw_total_resources[res_name] = aw_total * aw_count
            aw_pod_resources[res_name] = str(res_quantity)

        # https://stackoverflow.com/questions/1094841/get-human-readable-version-of-file-size
        def sizeof_fmt(num, suffix=""):
            for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
                if abs(num) < 1024.0:
                    return f"{num:3.1f}{unit}{suffix}"
                num /= 1024.0
            return f"{num:.1f}Yi{suffix}"

        summary += [f"""
# AppWrapper #{aw_index}:
#  - {aw_count} AppWrapper resource{'s' if aw_count > 1 else ''}, each creating:
#  - {aw_pod_count} Pod{'s' if aw_pod_count > 1 else ''}
#  - running for {aw_pod_runtime} seconds
#  - with {', '.join(f'{k}:{v}' for k, v in aw_pod_resources.items())} per pod (x{aw_pod_count})
#  - with {', '.join(f'{k}:{sizeof_fmt(v)}' for k, v in aw_total_resources.items())} per AppWrapper (x{aw_count})
#  - with {', '.join(f'{k}:{sizeof_fmt(v)}' for k, v in all_aw_total_resources.items())} for all these AppWrappers
"""]

        for aw_count_index in range(aw_count):
            appwrapper = copy.deepcopy(base_appwrapper)
            appwrapper_name = f"aw{aw_index:03d}-{aw_count_index:03d}-{aw_pod_runtime}s"

            set_config(appwrapper, "metadata.name", appwrapper_name)

            job = copy.deepcopy(job_template)
            job_name = f"{appwrapper_name}-job"
            set_config(job, "metadata.name", job_name)
            set_config(job, "spec.template.metadata.name", job_name + "-pod")
            set_config(job, "metadata.namespace", namespace)
            set_config(job, "spec.template.spec.containers[0].env[0].value", str(aw_pod_runtime))
            set_config(job, "spec.template.spec.containers[0].resources.limits", copy.deepcopy(aw_pod_resources))
            set_config(job, "spec.template.spec.containers[0].resources.requests", copy.deepcopy(aw_pod_resources))

            aw_genericitems = [dict(
                replicas = aw_pod_count,
                completionstatus = "Complete",
                custompodresources=[dict(
                    replicas=1,
                    requests=copy.deepcopy(aw_pod_resources),
                    limits=copy.deepcopy(aw_pod_resources),
                )],
                generictemplate = job,
            )]
            set_config(appwrapper, "spec.resources.GenericItems", aw_genericitems)

            print(f"""---
# AppWrapper config #{aw_index}, replica #{aw_count_index}:
#  - {aw_pod_count} Pods with {aw_pod_resources}
#  - running for {aw_pod_runtime} seconds
---
""")
            print(yaml.dump(appwrapper))

    print(f"---\n# Summary: {total_aw_count} AppWrappers over {total_aws_configs} configurations")
    print("\n".join(summary))
if __name__ == "__main__":
    sys.exit(main())

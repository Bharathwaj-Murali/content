import demistomock as demisto  # noqa: F401
from CommonServerPython import *  # noqa: F401


def algosec_get_network_object():
    resp = demisto.executeCommand("algosec-get-network-object", demisto.args())

    if isError(resp[0]):
        result = resp
    else:
        data = [demisto.get(entry, "Contents") for entry in resp]
        if data:
            data = data if isinstance(data, list) else [data]
            data = flattenTable(data)
            result = {"ContentsFormat": formats["table"], "Type": entryTypes["note"], "Contents": data}
        else:
            result = "No results."
    return_results(result)


def main():  # pragma: no cover
    try:
        algosec_get_network_object()
    except Exception as e:
        err_msg = f'Encountered an error while running the script: [{e}]'
        return_error(err_msg, error=e)


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()

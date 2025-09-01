import os
import requests
from typing import Any, Dict, Optional
from lxml import etree
from dotenv import load_dotenv
from zeep import Client, Settings
from zeep.cache import InMemoryCache
from zeep.helpers import serialize_object
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken

load_dotenv()

DEFAULT_SSL_VERIFY = True
DEFAULT_TIMEOUT = 30.0
DEFAULT_WSDL_URL = os.getenv("HEALTHCHECK_WSDL_URL", "http://example.com?wsdl")
SOAP_USERNAME = os.getenv("SOAP_USERNAME")
SOAP_PASSWORD = os.getenv("SOAP_PASSWORD")

# ----------------- In-memory caches -----------------
_wsdl_xml_cache: Dict[str, bytes] = {}
_operation_doc_cache: Dict[str, Dict[str, str]] = {}
_element_doc_cache: Dict[str, Dict[str, str]] = {}
_element_ns_map_cache: Dict[str, Dict[str, str]] = {}
_processed_wsdl_cache: Dict[tuple, dict] = {}

# ----------------- Cache management -----------------
def clear_cache():
    _wsdl_xml_cache.clear()
    _operation_doc_cache.clear()
    _element_doc_cache.clear()
    _element_ns_map_cache.clear()
    _processed_wsdl_cache.clear()

# ----------------- WSDL fetch with caching -----------------
def fetch_wsdl_xml(wsdl_url: str) -> bytes:
    if wsdl_url in _wsdl_xml_cache:
        return _wsdl_xml_cache[wsdl_url]
    resp = requests.get(wsdl_url, verify=False, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    _wsdl_xml_cache[wsdl_url] = resp.content
    return resp.content

# ----------------- Operation documentation lookup -----------------
def build_operation_doc_lookup(wsdl_url: str) -> Dict[str, str]:
    if wsdl_url in _operation_doc_cache:
        return _operation_doc_cache[wsdl_url]

    xml_bytes = fetch_wsdl_xml(wsdl_url)
    tree = etree.fromstring(xml_bytes)

    ns = {"wsdl": "http://schemas.xmlsoap.org/wsdl/"}
    lookup: Dict[str, str] = {}

    # Prefer logical docs from portType
    for op in tree.xpath(".//wsdl:portType/wsdl:operation", namespaces=ns):
        name = op.get("name")
        if not name:
            continue
        doc_nodes = op.xpath(".//*[local-name()='documentation']")
        if doc_nodes and doc_nodes[0].text:
            lookup[name] = doc_nodes[0].text.strip()

    # Fill in missing from binding
    for op in tree.xpath(".//wsdl:binding/wsdl:operation", namespaces=ns):
        name = op.get("name")
        if not name or name in lookup:
            continue
        doc_nodes = op.xpath(".//*[local-name()='documentation']")
        if doc_nodes and doc_nodes[0].text:
            lookup[name] = doc_nodes[0].text.strip()

    _operation_doc_cache[wsdl_url] = lookup
    return lookup

# ----------------- Element documentation lookup + namespace map -----------------
def build_element_doc_lookup(wsdl_url: str) -> Dict[str, str]:
    """
    Build a lookup of element docs keyed by namespace + parentType + elementName,
    and a parallel map of parentType:elementName -> namespace for lookup.
    """
    if wsdl_url in _element_doc_cache:
        return _element_doc_cache[wsdl_url]

    tree = etree.fromstring(fetch_wsdl_xml(wsdl_url))
    ns = {"xsd": "http://www.w3.org/2001/XMLSchema"}

    def _norm(txt: Optional[str]) -> str:
        return " ".join(txt.split()) if txt else ""

    lookup: Dict[str, str] = {}
    ns_map: Dict[str, str] = {}

    for el in tree.xpath(".//xsd:element[@name]", namespaces=ns):
        name = el.get("name")
        if not name:
            continue
        schema_nodes = el.xpath("ancestor-or-self::xsd:schema[1]", namespaces=ns)
        target_ns = schema_nodes[0].get("targetNamespace") if schema_nodes else ""
        parent_type_node = el.xpath("ancestor::xsd:complexType[1]", namespaces=ns)
        parent_type_name = parent_type_node[0].get("name") if parent_type_node else "GLOBAL"
        doc_nodes = el.xpath(".//*[local-name()='documentation']")
        doc_text = " ".join(
            _norm(d.text) for d in doc_nodes if d is not None and d.text and d.text.strip()
        )
        key = f"{target_ns}:{parent_type_name}:{name}"
        lookup[key] = doc_text
        ns_map[f"{parent_type_name}:{name}"] = target_ns

    _element_doc_cache[wsdl_url] = lookup
    _element_ns_map_cache[wsdl_url] = ns_map
    return lookup

# ----------------- Parameter parsing -----------------
def parse_elements(elements, wsdl_url: str, parent_type_name: str = "GLOBAL") -> Dict[str, Any]:
    if not elements:
        return {}
    docs = build_element_doc_lookup(wsdl_url)
    ns_map = _element_ns_map_cache.get(wsdl_url, {})
    result = {}
    for name, elm in elements:
        min_occurs = getattr(elm, "min_occurs", 1)
        max_occurs = getattr(elm, "max_occurs", 1)
        occurs = f"{min_occurs}-{'N' if max_occurs in (None, 'unbounded') else max_occurs}"
        raw_type = str(getattr(elm, "type", "") or "").replace("xs:", "").replace("xsd:", "")

        # Always get namespace from our precomputed map
        ns_part = ns_map.get(f"{parent_type_name}:{name}", "")
        doc_key = f"{ns_part}:{parent_type_name}:{name}"
        description = docs.get(doc_key)

        child_elements = getattr(getattr(elm, "type", None), "elements", None)
        if child_elements:
            child_type_qname = getattr(getattr(elm, "type", None), "qname", None)
            child_type_name = child_type_qname.localname if child_type_qname else "GLOBAL"
            result[name] = {
                "description": description,
                "occurs": occurs,
                **parse_elements(child_elements, wsdl_url, parent_type_name=child_type_name)
            }
        else:
            result[name] = {
                "type": raw_type,
                "description": description,
                "occurs": occurs
            }
    return result

# ----------------- Example payload builder -----------------
def build_example(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not params:
        return None
    ex = {}
    for k, v in params.items():
        if k in ("description", "occurs", "type"):
            continue
        if isinstance(v, dict) and "type" not in v:
            ex[k] = build_example(v)
        else:
            t = (v.get("type") or "").lower()
            if "datetime" in t:
                ex[k] = "2025-09-01T00:00:00"
            elif "date" in t:
                ex[k] = "2025-09-01"
            elif "string" in t:
                ex[k] = "string_value"
            elif "int" in t:
                ex[k] = 0
            elif "float" in t or "double" in t:
                ex[k] = 0.0
            elif "bool" in t:
                ex[k] = True
            elif v.get("occurs", "").endswith("-N"):
                ex[k] = []
            else:
                ex[k] = None
    return ex

# ----------------- Processed WSDL cache -----------------
def get_processed_wsdl(wsdl_url, username=None, password=None, version="v1", force_refresh=False):
    cache_key = (wsdl_url, username or SOAP_USERNAME, password or SOAP_PASSWORD, version)
    if not force_refresh and cache_key in _processed_wsdl_cache:
        return _processed_wsdl_cache[cache_key]

    transport = Transport(session=requests.Session(), cache=InMemoryCache(), timeout=DEFAULT_TIMEOUT)
    transport.session.verify = DEFAULT_SSL_VERIFY

    wsse = None
    user = username or SOAP_USERNAME
    pwd = password or SOAP_PASSWORD
    if user and pwd:
        wsse = UsernameToken(user, pwd)

    client = Client(
        wsdl=wsdl_url,
        transport=transport,
        settings=Settings(strict=False, xml_huge_tree=True),
        wsse=wsse
    )

    op_docs = build_operation_doc_lookup(wsdl_url)
    el_docs = build_element_doc_lookup(wsdl_url)

    _processed_wsdl_cache[cache_key] = {
        "client": client,
        "op_docs": op_docs,
        "el_docs": el_docs
    }
    return _processed_wsdl_cache[cache_key]

# ----------------- Core API -----------------
def describe_operations(wsdl_url=None, operation=None, username=None, password=None):
    wsdl_url = wsdl_url or DEFAULT_WSDL_URL
    processed = get_processed_wsdl(wsdl_url, username, password)
    client = processed["client"]
    op_docs = processed["op_docs"]

    service = next(iter(client.wsdl.services.values()))
    port = next(iter(service.ports.values()))
    ops = []
    for name, op in port.binding._operations.items():
        if operation and name != operation:
            continue
        params = parse_elements(
            op.input.body.type.elements if op.input else None,
            wsdl_url
        )
        ops.append({
            "operation": name,
            "description": op_docs.get(name),
            "input": params,
            "params_example": build_example(params)
        })
    return {"operations": ops}

def invoke_operation(wsdl_url, endpoint_url, operation, params, username=None, password=None):
    wsdl_url = wsdl_url or DEFAULT_WSDL_URL
    processed = get_processed_wsdl(wsdl_url, username, password)
    client = processed["client"]

    service = next(iter(client.wsdl.services.values()))
    port = next(iter(service.ports.values()))
    if operation not in port.binding._operations:
        raise ValueError(f"Unknown operation {operation}")
    proxy = client.create_service(port.binding.name, endpoint_url)
    result = getattr(proxy, operation)(**params)
    return serialize_object(result)

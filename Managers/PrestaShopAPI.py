"""Managers/PrestaShopAPI.py

PrestaShop Webservice API client.

Important: PrestaShop Webservice typically outputs JSON (optionally) but expects XML
payloads for write operations (PUT/POST). This client therefore uses JSON where safe
for reads and XML for updates.
"""

from __future__ import annotations

import requests
import re
from typing import Any, Dict, List, Optional, Tuple
from xml.dom import minidom


class PrestaShopAPI:
    """PrestaShop REST API client for product operations."""

    def __init__(self, base_url: str, api_key: str, logger=None):
        """
        Initialize PrestaShop API client.

        Args:
            base_url: PrestaShop store URL (e.g., "https://yourstore.com")
            api_key: API key from PrestaShop admin (Advanced Parameters → Webservice)
            logger: Optional logger instance

        Raises:
            ValueError: If base_url or api_key are invalid
        """
        self.base_url = self._normalize_base_url(base_url)
        self.api_key = self._validate_api_key(api_key)
        self.logger = logger
        self.session = requests.Session()
        self.session.auth = (self.api_key, '')
        self.session.headers.update({
            'Accept': 'application/json',
        })

        self._language_id_map_cache: Optional[Dict[str, str]] = None
        self._product_features_cache: Optional[List[Dict[str, Any]]] = None
        self._feature_name_to_id_cache: Optional[Dict[str, str]] = None
        self._feature_values_cache: Dict[str, List[Dict[str, Any]]] = {}
        # Best-effort diagnostics for UI-facing logs.
        # Example: {"status": 401, "method": "GET", "url": "...", "response_snippet": "..."}
        self.last_error: Optional[Dict[str, Any]] = None

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        """
        Normalize and validate base URL.

        Args:
            base_url: PrestaShop store URL

        Returns:
            Normalized URL without trailing slash or /api suffix

        Raises:
            ValueError: If URL is empty, invalid format, or not HTTPS
        """
        url = (base_url or "").strip().rstrip("/")

        # Validate URL is not empty
        if not url:
            raise ValueError("PrestaShop base URL cannot be empty")

        # Remove /api suffix if present
        if url.lower().endswith("/api"):
            url = url[:-4]

        # Validate URL format
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL format: '{url}'. Must start with http:// or https://")

        # Security: Enforce HTTPS for production use
        if not url.lower().startswith("https://"):
            raise ValueError(
                f"Insecure URL: '{url}'. PrestaShop API must use HTTPS to protect credentials. "
                "If testing locally, use https://localhost or configure SSL."
            )

        # Validate URL has a domain
        if url.lower() == "https://" or url.lower() == "http://":
            raise ValueError("Invalid URL: Missing domain name")

        return url

    @staticmethod
    def _validate_api_key(api_key: str) -> str:
        """
        Validate PrestaShop API key format.

        Args:
            api_key: API key to validate

        Returns:
            Validated API key (trimmed)

        Raises:
            ValueError: If API key is invalid
        """
        key = (api_key or "").strip()

        # Check if empty
        if not key:
            raise ValueError("PrestaShop API key cannot be empty")

        # Check for template/placeholder values
        if key == "TEMPLATE_API_KEY" or key == "YOUR_API_KEY_HERE":
            raise ValueError("PrestaShop API key is still set to template value. Please configure a real API key.")

        # PrestaShop API keys are typically 32 characters (alphanumeric)
        # Validate minimum length to catch obvious mistakes
        if len(key) < 32:
            raise ValueError(
                f"PrestaShop API key appears too short ({len(key)} chars). "
                "Valid keys are typically 32 characters. Please verify your key."
            )

        # Validate alphanumeric (PrestaShop keys are alphanumeric)
        if not key.isalnum():
            raise ValueError(
                "PrestaShop API key contains invalid characters. "
                "Valid keys contain only letters and numbers."
            )

        return key

    def _resp_snippet(self, response: requests.Response, limit: int = 800) -> str:
        try:
            text = response.text
        except Exception:
            return ""
        text = (text or "").strip()
        if len(text) > limit:
            return text[:limit] + "…"
        return text

    def _request(self, method: str, path: str, *, timeout: float = 25.0, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)

            # Some PrestaShop setups (or server configs) throw HTTP 500 when `output_format=JSON`
            # is requested on certain endpoints. Retry once without that parameter.
            try:
                params = kwargs.get("params")
                if (
                    response.status_code >= 500
                    and isinstance(params, dict)
                    and str(params.get("output_format") or "").upper() == "JSON"
                ):
                    fallback_params = dict(params)
                    fallback_params.pop("output_format", None)
                    self._log(
                        "Retrying without output_format=JSON",
                        method=method,
                        url=url,
                        status=response.status_code,
                    )
                    response2 = self.session.request(method, url, timeout=timeout, params=fallback_params, **{k: v for k, v in kwargs.items() if k != "params"})
                    # Prefer the fallback response if it is not a server error.
                    if response2.status_code < 500:
                        response = response2
            except Exception:
                # Best-effort fallback; keep original response.
                pass
        except Exception as e:
            self.last_error = {
                "kind": "exception",
                "method": method,
                "url": url,
                "error": str(e),
            }
            self._log(f"HTTP request failed: {method} {url}: {e}", method=method, url=url, error=str(e))
            raise

        if response.status_code >= 400:
            self.last_error = {
                "kind": "http",
                "method": method,
                "url": url,
                "status": response.status_code,
                "response_snippet": self._resp_snippet(response),
            }
            self._log(
                f"HTTP {response.status_code} for {method} {url}",
                method=method,
                url=url,
                status=response.status_code,
                response_snippet=self._resp_snippet(response),
            )
        return response

    def last_error_summary(self) -> str:
        """Human-readable last error for showing in UI logs."""
        err = self.last_error or {}
        kind = str(err.get("kind") or "").strip()
        if kind == "http":
            status = err.get("status")
            method = err.get("method")
            url = err.get("url")
            snippet = err.get("response_snippet")
            parts = [p for p in [f"HTTP {status}", str(method or "").strip(), str(url or "").strip()] if p]
            msg = " ".join(parts)
            if snippet:
                msg += f" | {snippet}"
            return msg
        if kind == "exception":
            method = err.get("method")
            url = err.get("url")
            e = err.get("error")
            parts = [p for p in ["Exception", str(method or "").strip(), str(url or "").strip(), str(e or "").strip()] if p]
            return " ".join(parts)
        if kind:
            return str(err.get("message") or kind)
        return ""

    def _log(self, message: str, **context):
        """Log a message if logger is available."""
        if self.logger:
            self.logger.log("PrestaShopAPI", message, **context)

    def test_connection(self) -> bool:
        """
        Test API connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self._request(
                "GET",
                "/api",
                params={'output_format': 'JSON'},
            )

            if response.status_code == 200:
                self._log("API connection successful")
                return True
            else:
                self._log(
                    f"API connection failed: {response.status_code}",
                    status=response.status_code,
                    response_snippet=self._resp_snippet(response),
                )
                return False
        except Exception as e:
            self._log(f"API connection error: {str(e)}", error=str(e))
            return False

    def search_product_by_reference(self, reference: str) -> Optional[int]:
        """
        Search for product by reference code.

        Note: In many PrestaShop setups the reference is stored on a combination
        (variant) rather than the base product. In that case `/api/products` with
        `filter[reference]` returns nothing, but `/api/combinations` can locate the
        combination and reveal its `id_product`.

        Args:
            reference: Product reference code

        Returns:
            Product ID if found, None otherwise
        """
        try:
            response = self._request(
                "GET",
                "/api/products",
                params={
                    'output_format': 'JSON',
                    'filter[reference]': reference,
                    'display': '[id]'
                },
            )

            if response.status_code != 200:
                self._log(
                    f"Search failed for {reference}: {response.status_code}",
                    reference=reference,
                    status=response.status_code,
                    response_snippet=self._resp_snippet(response),
                )
                return None

            # Prefer JSON, but fall back to XML if the shop doesn't support JSON output.
            try:
                data = response.json()
                products = data.get('products', [])
                if isinstance(products, dict) and 'product' in products:
                    products = products.get('product')
                if isinstance(products, dict):
                    products = [products]
                if products and len(products) > 0:
                    product_id = products[0].get('id')
                    self._log(f"Found product {reference}", product_id=product_id, reference=reference)
                    return int(product_id)
            except Exception:
                pass

            try:
                doc = minidom.parseString(response.content)
                product_nodes = doc.getElementsByTagName('product')
                if product_nodes:
                    node = product_nodes[0]
                    if node.hasAttribute('id'):
                        return int(node.getAttribute('id'))
                    id_nodes = node.getElementsByTagName('id')
                    if id_nodes and id_nodes[0].firstChild:
                        return int(id_nodes[0].firstChild.nodeValue)
            except Exception:
                pass

            # Fallback: the reference might be stored on a combination.
            try:
                comb_resp = self._request(
                    "GET",
                    "/api/combinations",
                    params={
                        'output_format': 'JSON',
                        'filter[reference]': reference,
                        'display': '[id,id_product]'
                    },
                )

                if comb_resp.status_code != 200:
                    self._log(
                        f"Combination search failed for {reference}: {comb_resp.status_code}",
                        reference=reference,
                        status=comb_resp.status_code,
                        response_snippet=self._resp_snippet(comb_resp),
                    )
                    return None

                # Prefer JSON, but fall back to XML if JSON output isn't supported.
                try:
                    data = comb_resp.json()
                    combos = data.get('combinations', [])
                    if isinstance(combos, dict) and 'combination' in combos:
                        combos = combos.get('combination')
                    if isinstance(combos, dict):
                        combos = [combos]
                    if combos:
                        id_product = combos[0].get('id_product')
                        if id_product:
                            self._log(
                                f"Found product via combination reference {reference}",
                                reference=reference,
                                product_id=id_product,
                            )
                            return int(id_product)
                except Exception:
                    pass

                try:
                    doc = minidom.parseString(comb_resp.content)
                    combo_nodes = doc.getElementsByTagName('combination')
                    if combo_nodes:
                        node = combo_nodes[0]
                        id_product_nodes = node.getElementsByTagName('id_product')
                        if id_product_nodes and id_product_nodes[0].firstChild:
                            id_product = id_product_nodes[0].firstChild.nodeValue
                            if id_product:
                                self._log(
                                    f"Found product via combination reference {reference}",
                                    reference=reference,
                                    product_id=id_product,
                                )
                                return int(id_product)
                except Exception:
                    pass
            except Exception as e:
                self._log(
                    f"Error searching combination for {reference}: {str(e)}",
                    reference=reference,
                    error=str(e),
                )

            self._log(f"Product not found: {reference}", reference=reference)
            return None

        except Exception as e:
            self._log(f"Error searching product {reference}: {str(e)}",
                     reference=reference, error=str(e))
            return None

    def get_product(self, product_id: int) -> Optional[Dict]:
        """
        Retrieve product by ID.

        Args:
            product_id: Product ID

        Returns:
            Product data dict if successful, None otherwise
        """
        try:
            response = self._request(
                "GET",
                f"/api/products/{product_id}",
                params={'output_format': 'JSON'},
            )

            if response.status_code == 200:
                data = response.json()
                self._log(f"Retrieved product {product_id}", product_id=product_id)
                return data.get('product', {})
            else:
                self._log(f"Failed to get product {product_id}: {response.status_code}",
                         product_id=product_id, status=response.status_code, response_snippet=self._resp_snippet(response))
                return None

        except Exception as e:
            self._log(f"Error getting product {product_id}: {str(e)}",
                     product_id=product_id, error=str(e))
            return None

    def _get_product_dom(self, product_id: int) -> Optional[minidom.Document]:
        """Fetch product as XML and return a DOM document."""
        try:
            response = self._request(
                "GET",
                f"/api/products/{product_id}",
                headers={'Accept': 'application/xml'},
            )
            if response.status_code != 200:
                return None
            return minidom.parseString(response.content)
        except Exception as e:
            self._log(f"Error getting product XML {product_id}: {e}", product_id=product_id, error=str(e))
            return None

    def _set_multilang_field(
        self,
        doc: minidom.Document,
        field_name: str,
        values_by_lang_id: Dict[str, str],
        *,
        use_cdata: bool,
    ) -> bool:
        try:
            product_nodes = doc.getElementsByTagName('product')
            if not product_nodes:
                return False
            product = product_nodes[0]

            field_nodes = [n for n in product.childNodes if getattr(n, 'tagName', None) == field_name]
            if not field_nodes:
                # Some payloads include nested nodes; fall back to global search under product.
                field_nodes = product.getElementsByTagName(field_name)
                if not field_nodes:
                    return False

            field = field_nodes[0]
            language_nodes = [n for n in field.childNodes if getattr(n, 'tagName', None) == 'language']
            updated_any = False

            for lang_id, value in (values_by_lang_id or {}).items():
                if value is None:
                    continue

                target = None
                for ln in language_nodes:
                    if str(ln.getAttribute('id')) == str(lang_id):
                        target = ln
                        break

                if target is None:
                    continue

                # Remove existing children
                while target.firstChild is not None:
                    target.removeChild(target.firstChild)

                if use_cdata:
                    target.appendChild(doc.createCDATASection(str(value)))
                else:
                    target.appendChild(doc.createTextNode(str(value)))
                updated_any = True

            return updated_any
        except Exception:
            return False

    def get_multilang_field_values(self, product_id: int, field_name: str) -> Dict[str, str]:
        """Return current values for a multi-language product field.

        Example fields: name, description, description_short.

        Returns dict mapping language id string to value.
        """
        values: Dict[str, str] = {}
        try:
            doc = self._get_product_dom(product_id)
            if doc is None:
                return values

            fields = doc.getElementsByTagName(field_name)
            if not fields:
                return values

            language_nodes = fields[0].getElementsByTagName('language')
            for ln in language_nodes:
                try:
                    lang_id = str(ln.getAttribute('id') or '').strip()
                    if not lang_id:
                        continue
                    parts: List[str] = []
                    for child in ln.childNodes:
                        if child.nodeType in (child.TEXT_NODE, child.CDATA_SECTION_NODE):
                            parts.append(child.data or '')
                    values[lang_id] = ''.join(parts)
                except Exception:
                    continue

        except Exception as e:
            self._log(
                f"Error reading multilang field {field_name} for product {product_id}: {e}",
                product_id=product_id,
                field=field_name,
                error=str(e),
            )
        return values

    def _put_product_dom(self, product_id: int, doc: minidom.Document) -> bool:
        """PUT an updated product XML document.

        PrestaShop Webservice may reject PUT payloads that contain non-writable fields
        (e.g. manufacturer_name). When that happens, it responds with HTTP 400 and an
        XML error like: parameter "<field>" not writable.

        We detect that case, strip the offending tags from the DOM, and retry.
        """

        def _strip_tag(tag_name: str) -> int:
            removed = 0
            try:
                nodes = list(doc.getElementsByTagName(tag_name))
                for n in nodes:
                    try:
                        parent = n.parentNode
                        if parent is not None:
                            parent.removeChild(n)
                            removed += 1
                    except Exception:
                        continue
            except Exception:
                return 0
            return removed

        # Best-effort proactive cleanup for a common offender.
        _strip_tag("manufacturer_name")

        try:
            for attempt in range(5):
                xml_bytes = doc.toxml(encoding='utf-8')
                response = self._request(
                    "PUT",
                    f"/api/products/{product_id}",
                    data=xml_bytes,
                    headers={'Content-Type': 'application/xml', 'Accept': 'application/xml'},
                )

                if response.status_code == 200:
                    return True

                # If PrestaShop complains about a non-writable parameter, remove it and retry.
                if response.status_code == 400:
                    snippet = ""
                    try:
                        snippet = (self.last_error or {}).get("response_snippet") or ""
                    except Exception:
                        snippet = ""

                    m = re.search(r'parameter\s+"([^"]+)"\s+not\s+writable', snippet, flags=re.IGNORECASE)
                    if m:
                        bad = (m.group(1) or "").strip()
                        if bad:
                            removed = _strip_tag(bad)
                            if removed > 0:
                                self._log(
                                    f"Stripped non-writable field(s) and retrying: {bad}",
                                    product_id=product_id,
                                    field=bad,
                                    removed=removed,
                                    attempt=attempt + 1,
                                )
                                continue

                return False

            return False

        except Exception as e:
            self._log(f"Error PUT product XML {product_id}: {e}", product_id=product_id, error=str(e))
            return False

    def update_product_name(self, product_id: int, names: Dict[str, str]) -> bool:
        """
        Update product name (multi-language).

        Args:
            product_id: Product ID
            names: Dict mapping language IDs to names {"1": "EN name", "2": "LT name", "3": "LV name"}

        Returns:
            True if successful, False otherwise
        """
        try:
            doc = self._get_product_dom(product_id)
            if doc is None:
                return False

            updated = self._set_multilang_field(doc, 'name', names, use_cdata=False)
            if not updated:
                self._log("No name fields updated (language IDs may not match shop)", product_id=product_id)
                self.last_error = {
                    "kind": "no_lang_match",
                    "message": "No <name>/<language id=...> nodes matched provided language IDs",
                    "product_id": product_id,
                    "provided_lang_ids": list((names or {}).keys()),
                }
                return False

            ok = self._put_product_dom(product_id, doc)
            if ok:
                self._log(f"Updated product {product_id} name", product_id=product_id)
                return True

            self._log(f"Failed to update product {product_id} name", product_id=product_id)
            if not self.last_error:
                self.last_error = {"kind": "unknown", "message": "PUT /api/products/<id> did not return 200"}
            return False

        except Exception as e:
            self._log(f"Error updating product {product_id} name: {e}", product_id=product_id, error=str(e))
            return False

    def update_product_description(self, product_id: int, descriptions: Dict[str, str]) -> bool:
        """
        Update product description (multi-language HTML).

        Args:
            product_id: Product ID
            descriptions: Dict mapping language IDs to HTML descriptions
                         {"1": "EN html", "2": "LT html", "3": "LV html"}

        Returns:
            True if successful, False otherwise
        """
        try:
            doc = self._get_product_dom(product_id)
            if doc is None:
                return False

            updated = self._set_multilang_field(doc, 'description', descriptions, use_cdata=True)
            if not updated:
                self._log("No description fields updated (language IDs may not match shop)", product_id=product_id)
                self.last_error = {
                    "kind": "no_lang_match",
                    "message": "No <description>/<language id=...> nodes matched provided language IDs",
                    "product_id": product_id,
                    "provided_lang_ids": list((descriptions or {}).keys()),
                }
                return False

            ok = self._put_product_dom(product_id, doc)
            if ok:
                self._log(f"Updated product {product_id} description", product_id=product_id)
                return True

            self._log(f"Failed to update product {product_id} description", product_id=product_id)
            if not self.last_error:
                self.last_error = {"kind": "unknown", "message": "PUT /api/products/<id> did not return 200"}
            return False

        except Exception as e:
            self._log(f"Error updating product {product_id} description: {e}", product_id=product_id, error=str(e))
            return False

    def update_product_short_description(self, product_id: int, descriptions_short: Dict[str, str]) -> bool:
        """Update product short description (multi-language HTML)."""
        try:
            doc = self._get_product_dom(product_id)
            if doc is None:
                return False

            updated = self._set_multilang_field(doc, 'description_short', descriptions_short, use_cdata=True)
            if not updated:
                self._log("No short description fields updated (language IDs may not match shop)", product_id=product_id)
                self.last_error = {
                    "kind": "no_lang_match",
                    "message": "No <description_short>/<language id=...> nodes matched provided language IDs",
                    "product_id": product_id,
                    "provided_lang_ids": list((descriptions_short or {}).keys()),
                }
                return False

            ok = self._put_product_dom(product_id, doc)
            if ok:
                self._log(f"Updated product {product_id} short description", product_id=product_id)
                return True

            self._log(f"Failed to update product {product_id} short description", product_id=product_id)
            if not self.last_error:
                self.last_error = {"kind": "unknown", "message": "PUT /api/products/<id> did not return 200"}
            return False

        except Exception as e:
            self._log(
                f"Error updating product {product_id} short description: {e}",
                product_id=product_id,
                error=str(e),
            )
            return False

    def get_language_id_map(self, force_refresh: bool = False) -> Dict[str, str]:
        """Return a map from ISO code (e.g. 'en', 'lt') to language id string.

        This avoids hard-coding IDs like 1/2/3 which vary by shop.
        """
        if self._language_id_map_cache is not None and not force_refresh:
            return self._language_id_map_cache

        mapping: Dict[str, str] = {}
        try:
            response = self._request(
                "GET",
                "/api/languages",
                params={'output_format': 'JSON', 'display': '[id,iso_code]'},
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    languages = data.get('languages', [])
                    if isinstance(languages, dict) and 'language' in languages:
                        languages = languages.get('language')
                    if isinstance(languages, dict):
                        languages = [languages]
                    if isinstance(languages, list):
                        for lang in languages:
                            iso = str(lang.get('iso_code', '')).strip().lower()
                            lid = str(lang.get('id', '')).strip()
                            if iso and lid:
                                mapping[iso] = lid
                except Exception:
                    pass

                if not mapping:
                    try:
                        doc = minidom.parseString(response.content)
                        for lang_node in doc.getElementsByTagName('language'):
                            iso_nodes = lang_node.getElementsByTagName('iso_code')
                            id_nodes = lang_node.getElementsByTagName('id')
                            if not iso_nodes or not id_nodes:
                                continue
                            iso = (iso_nodes[0].firstChild.nodeValue if iso_nodes[0].firstChild else '').strip().lower()
                            lid = (id_nodes[0].firstChild.nodeValue if id_nodes[0].firstChild else '').strip()
                            if iso and lid:
                                mapping[iso] = lid
                    except Exception:
                        pass

        except Exception:
            pass

        self._language_id_map_cache = mapping
        return mapping

    def _parse_multilang_json_field(self, field: Any) -> Dict[str, str]:
        """Best-effort parse of PrestaShop multilang JSON fields.

        PrestaShop JSON sometimes returns:
        - {"language": [{"id": "1", "value": "..."}, ...]}
        - [{"id": "1", "value": "..."}, ...]

        Returns mapping {lang_id: value}.
        """
        values: Dict[str, str] = {}
        try:
            if field is None:
                return values

            if isinstance(field, dict) and 'language' in field:
                return self._parse_multilang_json_field(field.get('language'))

            items: List[Any] = []
            if isinstance(field, list):
                items = field
            elif isinstance(field, dict):
                items = [field]
            else:
                return values

            for it in items:
                if not isinstance(it, dict):
                    continue
                lid = str(it.get('id') or it.get('@id') or '').strip()
                val = it.get('value')
                if val is None and '#text' in it:
                    val = it.get('#text')
                if lid and val is not None:
                    values[lid] = str(val)
        except Exception:
            return values
        return values

    @staticmethod
    def _norm_text(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip()).lower()

    def list_product_features(self) -> List[Dict[str, Any]]:
        """Return all product features with their multi-language names.

        Each item: {"id": "<id>", "name_by_lang": {"1": "...", ...}}
        """
        if self._product_features_cache is not None:
            return self._product_features_cache

        out: List[Dict[str, Any]] = []
        try:
            response = self._request(
                "GET",
                "/api/product_features",
                params={'output_format': 'JSON', 'display': 'full'},
            )
            if response.status_code != 200:
                return out
            try:
                data = response.json()
            except Exception:
                return out

            feats = data.get('product_features', [])
            if isinstance(feats, dict) and 'product_feature' in feats:
                feats = feats.get('product_feature')
            if isinstance(feats, dict):
                feats = [feats]
            if not isinstance(feats, list):
                return out

            for f in feats:
                if not isinstance(f, dict):
                    continue
                fid = str(f.get('id') or '').strip()
                if not fid:
                    continue
                name_by_lang = self._parse_multilang_json_field(f.get('name'))
                out.append({'id': fid, 'name_by_lang': name_by_lang})
        except Exception:
            return out
        self._product_features_cache = out
        return out

    def find_feature_id_by_names(self, names_by_lang_id: Dict[str, str]) -> Optional[str]:
        """Resolve a feature id by matching any provided language name."""
        try:
            needles = {self._norm_text(v): True for v in (names_by_lang_id or {}).values() if (v or '').strip()}
            if not needles:
                return None

            # Build cache once: normalized name -> feature id (across all languages).
            if self._feature_name_to_id_cache is None:
                cache: Dict[str, str] = {}
                for feat in self.list_product_features():
                    fid = str(feat.get('id') or '').strip()
                    if not fid:
                        continue
                    for v in (feat.get('name_by_lang') or {}).values():
                        k = self._norm_text(v)
                        if k and k not in cache:
                            cache[k] = fid
                self._feature_name_to_id_cache = cache

            cache = self._feature_name_to_id_cache or {}
            for k in needles.keys():
                if k in cache:
                    return cache[k]
        except Exception:
            return None
        return None

    def list_feature_values(self, feature_id: str) -> List[Dict[str, Any]]:
        """List all values for a given feature.

        Each item: {"id": "<value_id>", "id_feature": "<feature_id>", "value_by_lang": {...}}
        """
        fid = str(feature_id or '').strip()
        if not fid:
            return []

        if fid in self._feature_values_cache:
            return self._feature_values_cache[fid]

        out: List[Dict[str, Any]] = []
        try:
            response = self._request(
                "GET",
                "/api/product_feature_values",
                params={'output_format': 'JSON', 'display': 'full', 'filter[id_feature]': fid},
            )
            if response.status_code != 200:
                return out
            try:
                data = response.json()
            except Exception:
                return out

            vals = data.get('product_feature_values', [])
            if isinstance(vals, dict) and 'product_feature_value' in vals:
                vals = vals.get('product_feature_value')
            if isinstance(vals, dict):
                vals = [vals]
            if not isinstance(vals, list):
                return out

            for v in vals:
                if not isinstance(v, dict):
                    continue
                vid = str(v.get('id') or '').strip()
                if not vid:
                    continue
                id_feature = str(v.get('id_feature') or fid).strip()
                value_by_lang = self._parse_multilang_json_field(v.get('value'))
                out.append({'id': vid, 'id_feature': id_feature, 'value_by_lang': value_by_lang})
        except Exception:
            return out
        self._feature_values_cache[fid] = out
        return out

    def find_feature_value_id_by_values(self, feature_id: str, values_by_lang_id: Dict[str, str]) -> Optional[str]:
        """Resolve a feature value id by matching any provided language value."""
        try:
            needles = {self._norm_text(v): True for v in (values_by_lang_id or {}).values() if (v or '').strip()}
            if not needles:
                return None
            for val in self.list_feature_values(str(feature_id)):
                for v in (val.get('value_by_lang') or {}).values():
                    if self._norm_text(v) in needles:
                        return str(val.get('id'))
        except Exception:
            return None
        return None

    def create_feature_value(self, feature_id: str, values_by_lang_id: Dict[str, str]) -> Optional[str]:
        """Create a new product_feature_value for an existing feature.

        Returns newly created value id, or None.
        """
        fid = str(feature_id or '').strip()
        if not fid:
            return None
        try:
            doc = minidom.Document()
            root = doc.createElement('prestashop')
            root.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')
            doc.appendChild(root)

            pfv = doc.createElement('product_feature_value')
            root.appendChild(pfv)

            id_feature = doc.createElement('id_feature')
            id_feature.appendChild(doc.createTextNode(fid))
            pfv.appendChild(id_feature)

            custom = doc.createElement('custom')
            custom.appendChild(doc.createTextNode('0'))
            pfv.appendChild(custom)

            value_node = doc.createElement('value')
            pfv.appendChild(value_node)

            for lang_id, val in (values_by_lang_id or {}).items():
                if val is None:
                    continue
                lang_el = doc.createElement('language')
                lang_el.setAttribute('id', str(lang_id))
                lang_el.appendChild(doc.createCDATASection(str(val)))
                value_node.appendChild(lang_el)

            xml_bytes = doc.toxml(encoding='utf-8')
            response = self._request(
                'POST',
                '/api/product_feature_values',
                data=xml_bytes,
                headers={'Content-Type': 'application/xml', 'Accept': 'application/xml'},
            )

            if response.status_code not in (200, 201):
                return None

            try:
                resp_doc = minidom.parseString(response.content)
                nodes = resp_doc.getElementsByTagName('id')
                if nodes and nodes[0].firstChild:
                    return str(nodes[0].firstChild.nodeValue).strip()
            except Exception:
                pass

        except Exception:
            return None
        return None

    def update_product_feature_associations(self, product_id: int, feature_pairs: List[Tuple[str, str]]) -> bool:
        """Update product feature associations.

        feature_pairs: list of (feature_id, feature_value_id).

        Best-effort merge: updates/sets provided features, keeps unrelated existing ones.
        """
        try:
            doc = self._get_product_dom(int(product_id))
            if doc is None:
                return False

            product_nodes = doc.getElementsByTagName('product')
            if not product_nodes:
                return False
            product = product_nodes[0]

            # associations
            assoc = None
            for n in product.childNodes:
                if getattr(n, 'tagName', None) == 'associations':
                    assoc = n
                    break
            if assoc is None:
                assoc = doc.createElement('associations')
                product.appendChild(assoc)

            pf = None
            for n in assoc.childNodes:
                if getattr(n, 'tagName', None) == 'product_features':
                    pf = n
                    break
            if pf is None:
                pf = doc.createElement('product_features')
                assoc.appendChild(pf)

            # Parse existing associations
            existing: Dict[str, str] = {}
            schema_uses_id_feature = True
            for child in [c for c in pf.childNodes if getattr(c, 'tagName', None) == 'product_feature']:
                try:
                    id_feature = ''
                    id_feature_value = ''
                    id_nodes = child.getElementsByTagName('id')
                    id_feature_nodes = child.getElementsByTagName('id_feature')
                    id_feature_value_nodes = child.getElementsByTagName('id_feature_value')

                    if id_feature_nodes and id_feature_nodes[0].firstChild:
                        schema_uses_id_feature = True
                        id_feature = str(id_feature_nodes[0].firstChild.nodeValue).strip()
                    elif id_nodes and id_nodes[0].firstChild and id_feature_value_nodes and id_feature_value_nodes[0].firstChild:
                        # Some shops use <id> as feature id.
                        schema_uses_id_feature = False
                        id_feature = str(id_nodes[0].firstChild.nodeValue).strip()

                    if id_feature_value_nodes and id_feature_value_nodes[0].firstChild:
                        id_feature_value = str(id_feature_value_nodes[0].firstChild.nodeValue).strip()

                    if id_feature and id_feature_value:
                        existing[id_feature] = id_feature_value
                except Exception:
                    continue

            # Merge
            for fid, fvid in (feature_pairs or []):
                fid_s = str(fid or '').strip()
                fvid_s = str(fvid or '').strip()
                if not fid_s or not fvid_s:
                    continue
                existing[fid_s] = fvid_s

            # Clear and rebuild product_features
            for child in list(pf.childNodes):
                try:
                    pf.removeChild(child)
                except Exception:
                    continue

            for fid, fvid in existing.items():
                pf_item = doc.createElement('product_feature')

                if schema_uses_id_feature:
                    id_feature_el = doc.createElement('id_feature')
                    id_feature_el.appendChild(doc.createTextNode(str(fid)))
                    pf_item.appendChild(id_feature_el)
                else:
                    id_el = doc.createElement('id')
                    id_el.appendChild(doc.createTextNode(str(fid)))
                    pf_item.appendChild(id_el)

                id_fv_el = doc.createElement('id_feature_value')
                id_fv_el.appendChild(doc.createTextNode(str(fvid)))
                pf_item.appendChild(id_fv_el)

                pf.appendChild(pf_item)

            return self._put_product_dom(int(product_id), doc)

        except Exception as e:
            self._log(f"Error updating product feature associations: {e}", product_id=product_id, error=str(e))
            return False

    def bulk_update_products(self, updates: List[Dict]) -> Dict:
        """
        Bulk update multiple products.

        Args:
            updates: List of dicts with format:
                    [{"reference": "ABC123", "names": {...}, "descriptions": {...}}, ...]

        Returns:
            Dict with results: {'success': count, 'failed': count, 'errors': [...]}
        """
        results = {'success': 0, 'failed': 0, 'errors': []}

        for update in updates:
            reference = update.get('reference')
            names = update.get('names')
            descriptions = update.get('descriptions')

            # Find product ID by reference
            product_id = self.search_product_by_reference(reference)
            if not product_id:
                results['failed'] += 1
                results['errors'].append({
                    'reference': reference,
                    'error': 'Product not found'
                })
                continue

            # Update name if provided
            if names:
                if not self.update_product_name(product_id, names):
                    results['failed'] += 1
                    results['errors'].append({
                        'reference': reference,
                        'error': 'Failed to update name'
                    })
                    continue

            # Update description if provided
            if descriptions:
                if not self.update_product_description(product_id, descriptions):
                    results['failed'] += 1
                    results['errors'].append({
                        'reference': reference,
                        'error': 'Failed to update description'
                    })
                    continue

            results['success'] += 1

        self._log(f"Bulk update complete",
                 success=results['success'],
                 failed=results['failed'])

        return results

    def is_configured(self) -> bool:
        """Check if API is properly configured."""
        return bool(self.base_url and self.api_key and self.api_key != "TEMPLATE_API_KEY")

"""
Ownerclan fetcher
"""

import requests
from typing import Any, Dict, List, Optional

from dropshipping.suppliers.base import BaseFetcher


class OwnerclanFetcher(BaseFetcher):
    """Ownerclan supplier fetcher"""

    def __init__(self, storage, supplier_name, username, password, api_url, **kwargs):
        super().__init__(storage, supplier_name)
        self.username = username
        self.password = password
        self.api_url = api_url
        self.auth_url = "https://auth.ownerclan.com/auth"
        self.token = None
        self.timeout = kwargs.get("timeout", 30)

    def _get_token(self) -> str:
        """Authenticate and retrieve JWT token."""
        auth_data = {
            "service": "ownerclan",
            "userType": "seller",
            "username": self.username,
            "password": self.password,
        }
        response = requests.post(self.auth_url, json=auth_data, timeout=self.timeout)
        response.raise_for_status()
        # The token is returned as plain text
        self.token = response.text
        return self.token

    def _call_api(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """Helper to call the Ownerclan GraphQL API"""
        if not self.token:
            self._get_token()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        payload = {"query": query, "variables": variables or {}}
        response = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)

        # Re-authenticate on authorization error
        if response.status_code in [401, 403]:
            self._get_token()
            response = requests.post(
                self.api_url, json=payload, headers=headers, timeout=self.timeout
            )

        if response.status_code != 200:
            print(f"API Error: {response.status_code}")
            print(f"Response: {response.text}")
        response.raise_for_status()
        return response.json()

    def fetch_list(self, page: int) -> List[Dict]:
        """Fetch a list of products from Ownerclan"""
        # The API spec does not explicitly define a paginated list query.
        # This query is based on common GraphQL patterns and the detail query.
        # It might need adjustment based on the actual API schema.
        query = """
        query($first: Int, $after: String) {
            allItems(first: $first, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                edges {
                    node {
                        key
                        name
                        price
                        status
                    }
                }
            }
        }
        """
        # BaseFetcher uses page-based pagination, but Ownerclan uses cursor-based.
        # For now, we'll fetch the first page only, ignoring the 'page' argument.
        # A more robust solution would involve storing the cursor.
        variables = {"first": 100, "after": None}
        data = self._call_api(query, variables)
        # Extract nodes from edges
        edges = data.get("data", {}).get("allItems", {}).get("edges", [])
        return [edge["node"] for edge in edges]

    def fetch_detail(self, item_id: str) -> Dict:
        """Fetch details for a single product"""
        query = """
        query($key: ID!) {
            item(key: $key) {
                key
                name
                model
                production
                origin
                price
                fixedPrice
                category { name }
                shippingFee
                shippingType
                status
                options {
                    price
                    quantity
                    optionAttributes {
                        name
                        value
                    }
                }
                taxFree
                adultOnly
                returnable
                images
                createdAt
                updatedAt
            }
        }
        """
        variables = {"key": item_id}
        data = self._call_api(query, variables)
        return data.get("data", {}).get("item", {})

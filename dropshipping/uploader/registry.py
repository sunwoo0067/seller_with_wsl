"""
Uploader registry
"""

from typing import Dict, List, Type

from dropshipping.uploader.base import BaseUploader


class UploaderRegistry:
    """Uploader registry for marketplaces"""

    def __init__(self):
        self._uploaders: Dict[str, Type[BaseUploader]] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register default uploaders"""
        # TODO: Auto-discover and register uploaders
        try:
            from dropshipping.uploader.coupang_api import CoupangUploader

            self._uploaders["coupang"] = CoupangUploader
        except ImportError:
            pass

        try:
            from dropshipping.uploader.elevenst_api import ElevenstUploader

            self._uploaders["elevenst"] = ElevenstUploader
        except ImportError:
            pass

        try:
            from dropshipping.uploader.smartstore_api import SmartstoreUploader

            self._uploaders["smartstore"] = SmartstoreUploader
        except ImportError:
            pass

    def register(self, name: str, uploader_class: Type[BaseUploader]):
        """Register an uploader"""
        self._uploaders[name] = uploader_class

    def get_uploader(self, name: str, storage: "BaseStorage", config: "Settings") -> "BaseUploader":
        """Get uploader instance"""
        if name not in self._uploaders:
            raise ValueError(f"Unknown uploader: {name}")
        uploader_class = self._uploaders[name]
        return uploader_class(storage=storage, config=config)

    def list_uploaders(self) -> List[str]:
        """List registered uploaders"""
        return list(self._uploaders.keys())

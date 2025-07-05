# -*- coding: utf-8 -*-
"""Auction Excel uploader (shares with Gmarket)"""

from dropshipping.uploader.gmarket_excel.gmarket_excel_uploader import GmarketExcelUploader

# Auction uses the same Excel format as Gmarket
AuctionExcelUploader = GmarketExcelUploader

__all__ = ["AuctionExcelUploader"]

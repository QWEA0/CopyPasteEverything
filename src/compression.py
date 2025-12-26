# -*- coding: utf-8 -*-
"""
compression.py - Data compression module using zstd
Provides efficient compression/decompression for clipboard data transmission
"""

import base64
import zstandard as zstd
from typing import Tuple, Optional

# Compression settings
COMPRESSION_LEVEL = 3  # Balance between speed and compression ratio
MIN_COMPRESS_SIZE = 512  # Only compress data larger than this (bytes)

# Create reusable compressor/decompressor for better performance
_compressor = zstd.ZstdCompressor(level=COMPRESSION_LEVEL)
_decompressor = zstd.ZstdDecompressor()


def compress_data(data: bytes) -> Tuple[bytes, bool]:
    """
    Compress binary data using zstd.
    
    Args:
        data: Raw binary data to compress
        
    Returns:
        Tuple of (compressed_data, is_compressed)
        If data is too small, returns original data with is_compressed=False
    """
    if len(data) < MIN_COMPRESS_SIZE:
        return data, False
    
    compressed = _compressor.compress(data)
    
    # Only use compressed version if it's actually smaller
    if len(compressed) < len(data):
        return compressed, True
    
    return data, False


def decompress_data(data: bytes, is_compressed: bool) -> bytes:
    """
    Decompress binary data.
    
    Args:
        data: Compressed or raw binary data
        is_compressed: Whether the data is compressed
        
    Returns:
        Decompressed binary data
    """
    if not is_compressed:
        return data
    
    return _decompressor.decompress(data)


def encode_for_json(data: bytes) -> str:
    """
    Encode binary data to base64 string for JSON transmission.
    
    Args:
        data: Binary data
        
    Returns:
        Base64 encoded string
    """
    return base64.b64encode(data).decode('ascii')


def decode_from_json(data_str: str) -> bytes:
    """
    Decode base64 string back to binary data.
    
    Args:
        data_str: Base64 encoded string
        
    Returns:
        Binary data
    """
    return base64.b64decode(data_str)


def compress_and_encode(data: bytes) -> Tuple[str, bool]:
    """
    Compress data and encode to base64 for JSON transmission.
    
    Args:
        data: Raw binary data
        
    Returns:
        Tuple of (base64_encoded_string, is_compressed)
    """
    compressed, is_compressed = compress_data(data)
    encoded = encode_for_json(compressed)
    return encoded, is_compressed


def decode_and_decompress(data_str: str, is_compressed: bool) -> bytes:
    """
    Decode base64 string and decompress data.
    
    Args:
        data_str: Base64 encoded string
        is_compressed: Whether the data is compressed
        
    Returns:
        Original binary data
    """
    decoded = decode_from_json(data_str)
    return decompress_data(decoded, is_compressed)


def get_compression_stats(original_size: int, compressed_size: int) -> dict:
    """
    Calculate compression statistics.
    
    Args:
        original_size: Original data size in bytes
        compressed_size: Compressed data size in bytes
        
    Returns:
        Dictionary with compression statistics
    """
    if original_size == 0:
        return {
            'original_size': 0,
            'compressed_size': 0,
            'ratio': 1.0,
            'saved_bytes': 0,
            'saved_percent': 0.0
        }
    
    ratio = compressed_size / original_size
    saved = original_size - compressed_size
    
    return {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'ratio': ratio,
        'saved_bytes': saved,
        'saved_percent': (1 - ratio) * 100
    }


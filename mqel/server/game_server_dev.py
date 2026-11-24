#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MQEL game server with relaxed authentication for development/testing.

This version accepts any token for local connections to help diagnose issues.
DO NOT USE IN PRODUCTION!
"""

import sys
import os

# Add the server directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import original game_server module and modify it
from game_server import *

# Monkey-patch the token validation to accept any token for local connections
original_for_token = players.PlayerIndex.for_token

def relaxed_for_token(self, token, client_address):
    """Relaxed token validation - accepts any token for local connections."""
    # Accept any non-empty token for localhost
    if client_address == "127.0.0.1" and token:
        # Return the first player in the index or create a test player
        if self.index:
            return list(self.index.values())[0]
        else:
            # Create a temporary test player
            return Player("TestPlayer", client_address)
    return original_for_token(self, token, client_address)

# Apply the monkey-patch
players.PlayerIndex.for_token = relaxed_for_token

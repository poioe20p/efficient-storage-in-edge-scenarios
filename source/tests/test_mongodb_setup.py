#!/usr/bin/env python3
"""
Unit tests for MongoDB cluster setup modules.

These tests verify the module structure, imports, and basic functionality
without requiring actual MongoDB containers.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import subprocess

# Add source directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestModuleImports(unittest.TestCase):
    """Test that all modules can be imported correctly."""

    def test_import_config_server(self):
        """Test importing config_server module."""
        from sdn_controller.usecases.build_mongodb_cluster.config_server import ConfigServerManager
        self.assertIsNotNone(ConfigServerManager)

    def test_import_shard_replica_set(self):
        """Test importing shard_replica_set module."""
        from sdn_controller.usecases.build_mongodb_cluster.shard_replica_set import ShardReplicaSetManager
        self.assertIsNotNone(ShardReplicaSetManager)

    def test_import_router(self):
        """Test importing router module."""
        from sdn_controller.usecases.build_mongodb_cluster.router import RouterManager
        self.assertIsNotNone(RouterManager)

    def test_import_setup_cluster(self):
        """Test importing setup_cluster module."""
        from sdn_controller.usecases.build_mongodb_cluster.setup_cluster import setup_mongodb_cluster
        self.assertIsNotNone(setup_mongodb_cluster)

    def test_import_from_package(self):
        """Test importing from package __init__."""
        from sdn_controller.usecases.build_mongodb_cluster import (
            ConfigServerManager,
            ShardReplicaSetManager,
            RouterManager,
            setup_mongodb_cluster
        )
        self.assertIsNotNone(ConfigServerManager)
        self.assertIsNotNone(ShardReplicaSetManager)
        self.assertIsNotNone(RouterManager)
        self.assertIsNotNone(setup_mongodb_cluster)


class TestConfigServerManager(unittest.TestCase):
    """Test ConfigServerManager class."""

    def test_initialization(self):
        """Test ConfigServerManager initialization with default values."""
        from sdn_controller.usecases.build_mongodb_cluster.config_server import ConfigServerManager
        
        manager = ConfigServerManager()
        self.assertEqual(manager.container_name, "mongodb-config-server")
        self.assertEqual(manager.host, "192.168.100.4")
        self.assertEqual(manager.port, 27019)
        self.assertEqual(manager.replica_set_name, "configReplSet")

    def test_initialization_custom_values(self):
        """Test ConfigServerManager initialization with custom values."""
        from sdn_controller.usecases.build_mongodb_cluster.config_server import ConfigServerManager
        
        manager = ConfigServerManager(
            container_name="custom-config",
            host="10.0.0.1",
            port=27100,
            replica_set_name="customRS"
        )
        self.assertEqual(manager.container_name, "custom-config")
        self.assertEqual(manager.host, "10.0.0.1")
        self.assertEqual(manager.port, 27100)
        self.assertEqual(manager.replica_set_name, "customRS")


class TestShardReplicaSetManager(unittest.TestCase):
    """Test ShardReplicaSetManager class."""

    def test_initialization(self):
        """Test ShardReplicaSetManager initialization."""
        from sdn_controller.usecases.build_mongodb_cluster.shard_replica_set import ShardReplicaSetManager
        
        manager = ShardReplicaSetManager(
            container_name="mongodb-n1",
            host="10.0.0.4",
            port=27018,
            replica_set_name="rs_net1"
        )
        self.assertEqual(manager.container_name, "mongodb-n1")
        self.assertEqual(manager.host, "10.0.0.4")
        self.assertEqual(manager.port, 27018)
        self.assertEqual(manager.replica_set_name, "rs_net1")


class TestRouterManager(unittest.TestCase):
    """Test RouterManager class."""

    def test_initialization(self):
        """Test RouterManager initialization with default values."""
        from sdn_controller.usecases.build_mongodb_cluster.router import RouterManager
        
        manager = RouterManager()
        self.assertEqual(manager.container_name, "mongodb-router")
        self.assertEqual(manager.host, "192.168.100.4")
        self.assertEqual(manager.port, 27020)

    def test_initialization_custom_values(self):
        """Test RouterManager initialization with custom values."""
        from sdn_controller.usecases.build_mongodb_cluster.router import RouterManager
        
        manager = RouterManager(
            container_name="custom-router",
            host="10.0.0.1",
            port=27021
        )
        self.assertEqual(manager.container_name, "custom-router")
        self.assertEqual(manager.host, "10.0.0.1")
        self.assertEqual(manager.port, 27021)


class TestMockedOperations(unittest.TestCase):
    """Test operations with mocked subprocess calls."""

    @patch('subprocess.run')
    def test_config_server_check_status_initialized(self, mock_run):
        """Test checking replica set status when already initialized."""
        from sdn_controller.usecases.build_mongodb_cluster.config_server import ConfigServerManager
        
        # Mock successful response indicating already initialized
        mock_run.return_value = Mock(returncode=0, stdout="ALREADY_INITIALIZED\n", stderr="")
        
        manager = ConfigServerManager()
        status = manager.check_replica_set_status()
        
        self.assertEqual(status, "ALREADY_INITIALIZED")
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_config_server_check_status_not_initialized(self, mock_run):
        """Test checking replica set status when not initialized."""
        from sdn_controller.usecases.build_mongodb_cluster.config_server import ConfigServerManager
        
        # Mock response indicating not initialized
        mock_run.return_value = Mock(returncode=0, stdout="NOT_INITIALIZED\n", stderr="")
        
        manager = ConfigServerManager()
        status = manager.check_replica_set_status()
        
        self.assertEqual(status, "NOT_INITIALIZED")

    @patch('subprocess.run')
    def test_shard_replica_set_check_status(self, mock_run):
        """Test checking shard replica set status."""
        from sdn_controller.usecases.build_mongodb_cluster.shard_replica_set import ShardReplicaSetManager
        
        # Mock successful response
        mock_run.return_value = Mock(returncode=0, stdout="ALREADY_INITIALIZED\n", stderr="")
        
        manager = ShardReplicaSetManager(
            container_name="mongodb-n1",
            host="10.0.0.4",
            replica_set_name="rs_net1"
        )
        status = manager.check_replica_set_status()
        
        self.assertEqual(status, "ALREADY_INITIALIZED")


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())

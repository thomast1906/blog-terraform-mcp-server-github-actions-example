provider "azurerm" {
  features {}
  
  # Skip provider registration for local validation
  skip_provider_registration = true
}

# Resource Group
resource "azurerm_resource_group" "example" {
  name     = "rg-terraform-mcp-demo"
  location = "eastus"

  tags = {
    environment = "demo"
    managed_by  = "terraform"
  }
}

# Virtual Network
resource "azurerm_virtual_network" "example" {
  name                = "vnet-terraform-mcp"
  address_space       = ["10.0.0.0/18"]
  location            = azurerm_resource_group.example.location
  resource_group_name = azurerm_resource_group.example.name

  tags = {
    environment = "demo"
  }
}

# Subnet
resource "azurerm_subnet" "example" {
  name                 = "subnet-internal"
  resource_group_name  = azurerm_resource_group.example.name
  virtual_network_name = azurerm_virtual_network.example.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Storage Account
resource "azurerm_storage_account" "example" {
  name                     = "stmcpdemo${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.example.name
  location                 = azurerm_resource_group.example.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = {
    environment = "demo"
  }
}

# Random string for unique naming
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# App Service Plan
resource "azurerm_service_plan" "example" {
  name                = "asp-terraform-mcp-demo"
  resource_group_name = azurerm_resource_group.example.name
  location            = azurerm_resource_group.example.location
  os_type             = "Linux"
  sku_name            = "B1"

  tags = {
    environment = "demo"
  }
}

# Linux Web App
resource "azurerm_linux_web_app" "example" {
  name                = "app-terraform-mcp-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.example.name
  location            = azurerm_service_plan.example.location
  service_plan_id     = azurerm_service_plan.example.id

  site_config {
    application_stack {
      node_version = "18-lts"
    }
  }

  tags = {
    environment = "demo"
  }
}

# Output values
output "resource_group_name" {
  value       = azurerm_resource_group.example.name
  description = "The name of the resource group"
}

output "web_app_url" {
  value       = azurerm_linux_web_app.example.default_hostname
  description = "The default hostname of the web app"
}

output "storage_account_name" {
  value       = azurerm_storage_account.example.name
  description = "The name of the storage account"
}

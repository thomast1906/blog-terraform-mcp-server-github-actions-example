# Terraform MCP Server with GitHub Actions

This repository demonstrates using HashiCorp's Terraform MCP Server with GitHub Actions for automated Terraform validation and AI-enhanced analysis using GitHub Models.

## Overview

This example showcases how to:
- Validate Terraform plans using the official HashiCorp Terraform MCP Server
- Integrate AI-powered analysis using GitHub Models (GPT-4o)
- Automate validation in GitHub Actions CI/CD pipeline
- Deploy Azure infrastructure with best practices

## Features

- **MCP Server Integration**: Uses HashiCorp's official Terraform MCP Server for schema validation
- **AI-Enhanced Analysis**: Leverages GitHub Models for security and best practice recommendations
- **Azure Resources**: Example Terraform configuration deploying common Azure resources:
  - Resource Group
  - Virtual Network & Subnet
  - Storage Account
  - App Service Plan
  - Linux Web App

## GitHub Actions Workflow

The workflow (`terraform-mcp.yaml`) runs on pull requests and:
1. Starts the Terraform MCP Server using Docker
2. Runs `terraform init` and `terraform plan`
3. Validates resource schemas using MCP
4. Analyzes the plan with GitHub Models for security recommendations
5. Comments results on the PR

## Usage

1. Fork this repository
2. Create a pull request with Terraform changes
3. The workflow will automatically validate your changes
4. Review the MCP validation results and AI recommendations in the PR comments

## Requirements

- GitHub repository with Actions enabled
- Terraform 1.13.4+
- Azure subscription (for actual deployment)

## Local Testing

```bash
# Initialize Terraform
terraform init

# Create a plan
terraform plan -out=tfplan.binary

# View the plan
terraform show tfplan.binary
```

## MCP Server

This project uses the official HashiCorp Terraform MCP Server:
- Docker image: `hashicorp/terraform-mcp-server:latest`
- Provides provider schema validation
- Ensures configurations follow provider specifications

## GitHub Models

AI analysis is powered by GitHub Models, which provides:
- Security recommendations
- Best practice suggestions
- Resource configuration review
- No additional API keys required (uses GITHUB_TOKEN)

## License

MIT

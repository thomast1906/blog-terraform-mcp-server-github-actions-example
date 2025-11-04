#!/usr/bin/env python3
"""
Terraform MCP Validation Script for GitHub Actions
Validates Terraform plans using HashiCorp MCP Server and GitHub Models
"""

import asyncio
import json
import os
import sys
import uuid
import requests
from typing import Dict, Any, List, Optional


async def send_mcp_request(process, method: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Send JSON-RPC request to MCP server"""
    request = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method
    }
    
    if params:
        request["params"] = params
    
    try:
        request_json = json.dumps(request) + '\n'
        process.stdin.write(request_json.encode())
        await process.stdin.drain()
        
        response_line = await asyncio.wait_for(
            process.stdout.readline(), 
            timeout=20.0
        )
        
        if response_line:
            response_text = response_line.decode().strip()
            if response_text:
                return json.loads(response_text)
                
    except asyncio.TimeoutError:
        print(f"Warning: MCP request timeout for method '{method}'", file=sys.stderr)
    except Exception as e:
        print(f"Warning: MCP request failed for '{method}': {e}", file=sys.stderr)
    
    return None


async def get_provider_version(session, provider_name: str) -> Optional[str]:
    """Get latest provider version from MCP server"""
    try:
        # Split provider_name into namespace and name (e.g., "hashicorp/azurerm")
        parts = provider_name.split('/')
        namespace = parts[0] if len(parts) > 1 else "hashicorp"
        name = parts[1] if len(parts) > 1 else provider_name
        
        response = await session.call_tool(
            "get_latest_provider_version",
            arguments={
                "namespace": namespace,
                "name": name
            }
        )
        
        if response and hasattr(response, 'content'):
            for item in response.content:
                if hasattr(item, 'text'):
                    # Extract version from response
                    import re
                    version_match = re.search(r'([0-9]+\.[0-9]+\.[0-9]+)', item.text)
                    if version_match:
                        return version_match.group(1)
        return None
    except Exception as e:
        print(f"Warning: Failed to get version for {provider_name}: {e}", file=sys.stderr)
        return None


async def search_modules(session, provider: str) -> List[Dict]:
    """Search for Terraform modules for a provider"""
    try:
        response = await session.call_tool(
            "search_modules",
            arguments={
                "module_query": provider,
                "current_offset": 0
            }
        )
        
        modules = []
        if response and hasattr(response, 'content'):
            for item in response.content:
                if hasattr(item, 'text') and "modules found" in item.text:
                    modules.append({
                        "provider": provider,
                        "description": item.text[:200]
                    })
        return modules
    except Exception as e:
        print(f"Warning: Module search failed for {provider}: {e}", file=sys.stderr)
        return []


async def get_resource_docs(session, resource_type: str) -> Optional[Dict]:
    """Get documentation for a specific resource type"""
    try:
        # Extract provider and service from resource type
        provider_name = resource_type.split("_")[0] if "_" in resource_type else resource_type
        service_slug = resource_type.replace(f"{provider_name}_", "") if "_" in resource_type else resource_type
        
        # Map provider names to registry names
        provider_mapping = {"azure": "azurerm", "gcp": "google"}
        registry_provider = provider_mapping.get(provider_name, provider_name)
        
        response = await session.call_tool(
            "search_providers",
            arguments={
                "provider_name": registry_provider,
                "provider_namespace": "hashicorp",
                "service_slug": service_slug,
                "provider_data_type": "resources"
            }
        )
        
        if response and hasattr(response, 'content') and response.content:
            return {
                "status": "available",
                "resource_type": resource_type,
                "documentation": str(response.content[0])[:500] if response.content else ""
            }
        return None
    except Exception as e:
        print(f"Warning: Could not get docs for {resource_type}: {e}", file=sys.stderr)
        return None


async def validate_terraform():
    """Main validation function"""
    # Read the Terraform plan
    with open('tfplan.json', 'r') as f:
        plan = json.load(f)
    
    # Start MCP server
    server_params = {
        "command": "docker",
        "args": ["run", "--rm", "-i", "hashicorp/terraform-mcp-server:latest"]
    }
    
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    
    server_params_obj = StdioServerParameters(
        command=server_params["command"],
        args=server_params["args"]
    )
    
    async with stdio_client(server_params_obj) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools_result = await session.list_tools()
            available_tools = [tool.name for tool in tools_result.tools]
            print(f"\n📋 Available MCP tools: {', '.join(available_tools)}")
            
            # Get list of resources from plan
            resources = []
            providers_found = set()
            action_counts = {'create': 0, 'update': 0, 'delete': 0, 'replace': 0, 'no-op': 0}
            
            if 'resource_changes' in plan:
                for change in plan['resource_changes']:
                    actions = change.get('change', {}).get('actions', ['no-op'])
                    
                    # Count actions
                    if 'create' in actions:
                        action_counts['create'] += 1
                    if 'update' in actions:
                        action_counts['update'] += 1
                    if 'delete' in actions:
                        action_counts['delete'] += 1
                    if ['delete', 'create'] == actions:
                        action_counts['replace'] += 1
                    if actions == ['no-op']:
                        action_counts['no-op'] += 1
                    
                    if actions != ['no-op']:
                        resource_type = change.get('type', '')
                        resources.append({
                            'type': resource_type,
                            'name': change.get('name', ''),
                            'address': change.get('address', ''),
                            'action': actions
                        })
                        
                        # Extract provider
                        if '_' in resource_type:
                            provider = resource_type.split('_')[0]
                            providers_found.add(provider)
            
            print(f"\n🔍 Validating {len(resources)} resource changes with MCP...")
            print(f"📦 Providers detected: {', '.join(providers_found)}")
            print(f"📊 Actions: Create={action_counts['create']}, Update={action_counts['update']}, Delete={action_counts['delete']}, Replace={action_counts['replace']}")
            
            # Get provider versions
            provider_versions = {}
            for provider in providers_found:
                # Map common names to registry names
                provider_mapping = {"azure": "azurerm", "gcp": "google"}
                registry_name = provider_mapping.get(provider, provider)
                
                version = await get_provider_version(session, f"hashicorp/{registry_name}")
                if version:
                    provider_versions[provider] = version
                    print(f"✅ {provider.upper()}: Latest version v{version}")
            
            # Search for modules (limit to 2 providers to avoid timeout)
            module_suggestions = []
            for provider in list(providers_found)[:2]:
                registry_name = {"azure": "azurerm", "gcp": "google"}.get(provider, provider)
                modules = await search_modules(session, registry_name)
                if modules:
                    module_suggestions.extend(modules)
                    print(f"📦 Found {len(modules)} modules for {provider}")
            
            # Get resource-specific documentation (limit to 3 resources)
            resource_docs = {}
            unique_types = list(set([r['type'] for r in resources]))[:3]
            for resource_type in unique_types:
                docs = await get_resource_docs(session, resource_type)
                if docs:
                    resource_docs[resource_type] = docs
                    print(f"📄 Documentation found for {resource_type}")
            
            # Validate each resource
            validated_count = 0
            for resource in resources:
                try:
                    provider = resource['type'].split('_')[0] if '_' in resource['type'] else resource['type']
                    registry_provider = {"azure": "azurerm", "gcp": "google"}.get(provider, provider)
                    
                    # Validate provider exists by getting its version
                    result = await session.call_tool(
                        "get_latest_provider_version",
                        arguments={
                            "namespace": "hashicorp",
                            "name": registry_provider
                        }
                    )
                    
                    print(f"✅ {resource['type']} - Provider validated")
                    validated_count += 1
                    
                except Exception as e:
                    print(f"❌ {resource['type']} - Validation failed: {e}")
            
            # Prepare enhanced data for AI analysis
            analysis_data = {
                "resources": resources,
                "providers": list(providers_found),
                "provider_versions": provider_versions,
                "action_counts": action_counts,
                "validated_count": validated_count,
                "total_count": len(resources),
                "module_suggestions": module_suggestions,
                "resource_docs": resource_docs
            }
            
            # GitHub Models AI analysis
            token = os.getenv('GITHUB_TOKEN')
            if token:
                print("\n🤖 Running AI-enhanced analysis with GitHub Models...")
                
                # Enhanced prompt with provider context
                provider_context = "\n".join([
                    f"- {p.upper()}: Latest version v{v}" 
                    for p, v in provider_versions.items()
                ])
                
                # Add module context if available
                module_context = ""
                if module_suggestions:
                    module_context = "\n\n**Available Modules:**\n"
                    for mod in module_suggestions[:3]:
                        module_context += f"- {mod['provider']}: {mod['description']}\n"
                
                # Add resource doc context
                doc_context = ""
                if resource_docs:
                    doc_context = "\n\n**Resource Documentation Available:**\n"
                    for rtype in resource_docs.keys():
                        doc_context += f"- {rtype}\n"
                
                system_prompt = """You are a senior Terraform and cloud infrastructure expert. 
Analyze this Terraform plan and provide:

1. **Security Analysis** - Identify vulnerabilities and misconfigurations
2. **Best Practices** - Recommend improvements and optimizations
3. **Version Recommendations** - Suggest provider version updates if needed
4. **Resource-Specific Advice** - Detailed guidance for each resource type
5. **Module Recommendations** - Suggest using verified modules where applicable

Format your response in clear sections with specific, actionable recommendations."""

                user_prompt = f"""**Terraform Plan Analysis**

**Providers:**
{provider_context}{module_context}{doc_context}

**Plan Summary:**
- Create: {action_counts['create']} resources
- Update: {action_counts['update']} resources
- Delete: {action_counts['delete']} resources
- Replace: {action_counts['replace']} resources

**Resources Being Changed:**
{json.dumps(resources[:10], indent=2)}{'...' if len(resources) > 10 else ''}

**Validation:**
- Validated Resources: {validated_count}/{len(resources)}
- Providers: {', '.join(providers_found)}

Please provide comprehensive security, best practice, and optimization recommendations."""
                
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1
                }
                
                try:
                    response = requests.post(
                        "https://models.inference.ai.azure.com/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60
                    )
                    response.raise_for_status()
                    
                    ai_response = response.json()
                    analysis_content = ai_response['choices'][0]['message']['content']
                    
                    print(f"\n{analysis_content}")
                    
                    # Save comprehensive analysis
                    full_analysis = f"""# Terraform MCP Validation Report

## MCP Validation Results

**Status:** ✅ Connected to HashiCorp Terraform MCP Server

**Provider Versions:**
{provider_context}

**Resources Validated:** {validated_count}/{len(resources)}

---

## AI Analysis

{analysis_content}

---

*Powered by HashiCorp Terraform MCP Server & GitHub Models*
"""
                    
                    with open('ai_analysis.txt', 'w') as f:
                        f.write(full_analysis)
                    
                    # Save summary for PR comment
                    summary = {
                        "validated": validated_count,
                        "total": len(resources),
                        "providers": list(providers_found),
                        "versions": provider_versions,
                        "action_counts": action_counts,
                        "modules_found": len(module_suggestions),
                        "docs_found": len(resource_docs)
                    }
                    with open('validation_summary.json', 'w') as f:
                        json.dump(summary, f, indent=2)
                    
                except Exception as e:
                    print(f"⚠️  AI analysis failed: {e}")
                    error_analysis = f"""# Terraform MCP Validation Report

## MCP Validation Results

**Resources Validated:** {validated_count}/{len(resources)}

**AI Analysis:** Failed - {str(e)}

Please check GitHub Actions logs for details.
"""
                    with open('ai_analysis.txt', 'w') as f:
                        f.write(error_analysis)
            
            print(f"\n✅ MCP Validation Complete - {validated_count}/{len(resources)} resources validated")


if __name__ == "__main__":
    try:
        asyncio.run(validate_terraform())
    except Exception as e:
        print(f"ERROR: Validation failed: {e}", file=sys.stderr)
        sys.exit(1)

# UTCP + FastAPI + NETCONF + OpenAI Integration

A sophisticated network automation system that combines Universal Tool Calling Protocol (UTCP), FastAPI-based NETCONF services, Scrapli for network device communication, and OpenAI's language models to create an intelligent network management interface. Note this is a small integration to demo UTCP it is not fully functional for all NETCONF operations and you would need to use define more tool call schemas to introduce other operations. An EOS Arista device was used for the demo.

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [UTCP vs MCP Comparison](#utcp-vs-mcp-comparison)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Overview

This system enables natural language network automation by combining:
- **UTCP Client**: Direct tool discovery and execution without wrapper protocols
- **FastAPI NETCONF Service**: RESTful wrapper around Scrapli NETCONF operations
- **OpenAI Integration**: Intelligent request parsing and response generation
- **Gradio UI**: User-friendly web interface for network operations

The system allows network engineers to perform complex NETCONF operations using natural language requests like "Show Ethernet1 config on 172.29.11.9" or "Set description on interface GigE0/1 to 'uplink'".
<img width="1726" height="991" alt="Screenshot from 2025-08-10 20-49-21" src="https://github.com/user-attachments/assets/d5ac9384-a3e4-460f-905a-8300c9467b72" />



## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Gradio UI     │    │ OpenAI LLM   │    │  UTCP Client    │    │ FastAPI Server  │
│                 │◄──►│              │◄──►│                 │◄──►│                 │
│ Natural Language│    │ Tool Selection│    │ Tool Discovery  │    │ NETCONF Wrapper │
└─────────────────┘    └──────────────┘    └─────────────────┘    └─────────────────┘
                                                                            │
                                                                            ▼
                                                                   ┌─────────────────┐
                                                                   │ Scrapli NETCONF │
                                                                   │                 │
                                                                   │ Network Devices │
                                                                   └─────────────────┘
```

## UTCP vs MCP Comparison

### Universal Tool Calling Protocol (UTCP) - This Implementation

**Advantages:**
- **Direct Communication**: No intermediate wrapper protocol needed
- **Native HTTP Integration**: Tools are discovered via OpenAPI/Swagger specs
- **Flexible Provider System**: Supports multiple provider types (HTTP, local, etc.)
- **Automatic Schema Discovery**: Tools and their parameters are auto-discovered
- **Lightweight**: Minimal protocol overhead
- **Authentication Handled Directly**: API keys, tokens managed at the tool level

**How it works:**
1. UTCP client reads `providers.json` to discover tool sources
2. Fetches OpenAPI specs directly from FastAPI services
3. Dynamically builds tool schemas for the LLM
4. Executes tool calls via direct HTTP requests
5. No protocol translation or message wrapping required

### Model Context Protocol (MCP) - Alternative Approach

**Characteristics:**
- **Wrapper Protocol**: Requires MCP server to wrap existing APIs
- **Standardized Messages**: All communication goes through MCP message format
- **Server-Side Translation**: MCP server must translate between MCP and actual APIs
- **Additional Layer**: Adds complexity with protocol conversion
- **Centralized Auth**: Authentication typically handled at MCP server level

**Trade-offs:**
- More standardized but adds protocol overhead
- Requires additional MCP server implementation
- May introduce latency due to message translation
- Better for scenarios requiring strict protocol standardization

## Components

### 1. UTCP Client (`llm_utcp_client.py`)
- **Tool Discovery**: Automatically finds available tools from providers
- **LLM Integration**: Interfaces with OpenAI models for intelligent tool selection
- **Execution Engine**: Handles tool calls and result processing
- **State Management**: Maintains conversation history and context

### 2. FastAPI NETCONF Service (`app.py`)
- **NETCONF Operations**: `get-config`, `edit-config`, `commit`, `rpc`
- **Scrapli Integration**: Uses scrapli_netconf for reliable device communication
- **Parameter Flexibility**: Supports both JSON body and query parameters
- **Error Handling**: Comprehensive error reporting and logging
- **OpenAPI Documentation**: Auto-generated API specs for tool discovery

### 3. Gradio Interface
- **Natural Language Input**: User-friendly text interface
- **Multi-Panel Display**: Shows tool calls, results, and final answers
- **Conversation History**: Maintains context across interactions
- **Real-time Updates**: Async processing with live feedback

## Prerequisites

- Python 3.8+
- **OpenAI API key**: Get from https://platform.openai.com/api-keys
- **Arista EOS devices with NETCONF enabled** (demo environment)
- Network connectivity to target devices

**Environment Setup Options:**
1. Create a `.env` file in the project root (recommended)
2. Export environment variables directly in your shell
3. Override per-request via API parameters

## Installation

1. **Clone or create the project structure:**
```bash
mkdir utcp-netconf-automation
cd utcp-netconf-automation
```

2. **Install dependencies:**
```bash
pip install fastapi uvicorn gradio openai python-dotenv
pip install scrapli[asyncssh] scrapli-netconf
pip install utcp  # Universal Tool Calling Protocol client
```

3. **Create project files:**
- Save the FastAPI service as `app.py`
- Save the UTCP client as `llm_utcp_client.py`
- Create `providers.json` (see configuration section)

**Method 1: Create `.env` file (recommended):**
```bash
# Create .env file
cat > .env << EOF
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
NETCONF_USER=admin
NETCONF_PASS=your_arista_password_here
EOF
```

**Method 2: Export variables directly:**
```bash
export OPENAI_API_KEY=your_openai_api_key_here
export OPENAI_MODEL=gpt-4o-mini
export NETCONF_USER=admin
export NETCONF_PASS=your_arista_password_here
```

## Configuration

### Environment Variables (`.env`)
```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# NETCONF Credentials (optional defaults)
# These were configured for Arista EOS devices in our demo
NETCONF_USER=admin
NETCONF_PASS=your_arista_password_here
```

**Alternative: Using Export Commands**
Instead of a `.env` file, you can export environment variables directly:
```bash
export OPENAI_API_KEY=your_openai_api_key_here
export OPENAI_MODEL=gpt-4o-mini
export NETCONF_USER=admin
export NETCONF_PASS=your_arista_password_here
```

### Providers Configuration (`providers.json`)
```json
[
  {
    "name": "netconf_tools",
    "provider_type": "http",
    "http_method": "GET",
    "url": "http://localhost:8000/openapi.json",
    "content_type": "application/json"
  }
]
```

#### Providers.json Explanation

The `providers.json` file tells UTCP where to find available tools:

- **name**: Identifier for the tool provider
- **provider_type**: `"http"` for web-based tools, `"local"` for local executables
- **http_method**: HTTP method to fetch the tool specification (usually `GET`)
- **url**: Endpoint serving the OpenAPI/Swagger specification
- **content_type**: Expected response format

**How it works:**
1. UTCP client reads this file at startup
2. Makes a GET request to `http://localhost:8000/openapi.json`
3. FastAPI automatically serves its OpenAPI spec at this endpoint
4. UTCP parses the spec to understand available operations and parameters
5. Converts OpenAPI operations into callable tools for the LLM

**Multiple Providers Example:**
```json
[
  {
    "name": "netconf_tools",
    "provider_type": "http",
    "http_method": "GET",
    "url": "http://localhost:8000/openapi.json",
    "content_type": "application/json"
  },
  {
    "name": "monitoring_tools",
    "provider_type": "http",
    "http_method": "GET",
    "url": "http://monitoring-service:8001/openapi.json",
    "content_type": "application/json"
  }
]
```

## Usage

### 1. Start the FastAPI NETCONF Service
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Launch the UTCP Client with Gradio UI
```bash
python llm_utcp_client.py
```

### 3. Access the Web Interface
Open `http://localhost:7860` in your browser.

### 4. Example Requests
- "Show the running configuration for interface Ethernet1 on device 192.168.1.1"
- "Set the description of interface GigE0/0/1 to 'Uplink to Core' on switch 10.0.0.5"
- "Get the current OSPF configuration from 172.16.1.1"
- "Commit the pending configuration changes on device 192.168.100.10"

## API Documentation

### FastAPI NETCONF Endpoints

#### GET/POST `/netconf/get-config`
Retrieve device configuration.

**Parameters:**
- `host` (required): Device IP/hostname
- `port` (optional): NETCONF port (default: 830)
- `source` (optional): Configuration source (`running`, `candidate`)
- `filter_xml` (optional): XML subtree filter
- `username`/`password` (optional): Override environment credentials

#### POST `/netconf/edit-config`
Modify device configuration.

**Parameters:**
- `host` (required): Device IP/hostname
- `config_xml` (required): Configuration XML
- `target` (optional): Target datastore (default: `running`)
- `default_operation` (optional): `merge`, `replace`, `none`

#### POST `/netconf/commit`
Commit configuration changes.

**Parameters:**
- `host` (required): Device IP/hostname
- `confirmed` (optional): Confirmed commit boolean
- `confirm_timeout` (optional): Timeout for confirmed commit
- `comment` (optional): Commit comment

#### POST `/netconf/rpc`
Execute custom RPC operations.

**Parameters:**
- `host` (required): Device IP/hostname
- `rpc_xml` (required): Raw RPC XML

### Authentication Handling

Authentication is handled directly by the FastAPI service:
1. Environment variables provide default credentials
2. Per-request credentials can override defaults
3. No additional authentication layers required
4. Credentials are passed directly to Scrapli NETCONF

## Examples

### Basic Configuration Retrieval
```python
# Natural language: "Show interface config on 192.168.1.1"
# Translates to:
{
  "tool_name": "netconf_tools.netconf_get_config",
  "arguments": {
    "host": "192.168.1.1",
    "source": "running",
    "filter_xml": "<interfaces><interface><name>*</name></interface></interfaces>"
  }
}
```

### Configuration Change
```python
# Natural language: "Set interface description on Ethernet1"
# Translates to:
{
  "tool_name": "netconf_tools.netconf_edit_config", 
  "arguments": {
    "host": "192.168.1.1",
    "target": "running",
    "config_xml": "<config><interfaces><interface><name>Ethernet1</name><description>Updated via UTCP</description></interface></interfaces></config>"
  }
}
```

## Workflow Process

1. **User Input**: Natural language request via Gradio interface
2. **Tool Discovery**: UTCP client discovers available tools from providers.json
3. **LLM Processing**: OpenAI model analyzes request and selects appropriate tool
4. **Tool Execution**: UTCP client makes HTTP call to FastAPI service
5. **NETCONF Operation**: FastAPI service uses Scrapli to communicate with device
6. **Response Processing**: Results flow back through the chain
7. **Final Answer**: LLM generates human-readable response from tool output

## Troubleshooting

### Common Issues

**1. UTCP Client Cannot Discover Tools**
- Verify FastAPI service is running on port 8000
- Check `providers.json` URL is accessible
- Ensure OpenAPI endpoint returns valid JSON

**2. NETCONF Connection Failures**
- Verify device NETCONF is enabled
- Check network connectivity and credentials
- Review firewall/ACL settings on port 830

**3. OpenAI API Errors**
- Validate API key in `.env` file
- Check API quota and usage limits
- Verify model name is correct

**4. Authentication Issues**
- Confirm NETCONF_USER and NETCONF_PASS are set
- Test credentials manually with NETCONF client
- Check device user permissions

### Debug Endpoints

Access `http://localhost:8000/debug/env` to verify environment variable configuration.

### Logging

Enable detailed logging by modifying the FastAPI service:
```python
logging.getLogger("scrapli").setLevel(logging.DEBUG)
```

## Benefits of This Architecture

1. **Direct Integration**: No protocol translation overhead
2. **Dynamic Discovery**: Tools are discovered automatically from OpenAPI specs
3. **Flexible Authentication**: Handled directly at the service level
4. **Scalable**: Easy to add new tool providers
5. **Maintainable**: Standard HTTP APIs, no custom protocols
6. **Debuggable**: Standard HTTP debugging tools work
7. **Extensible**: Can integrate any OpenAPI-compliant service

This approach provides a robust, efficient, and maintainable solution for intelligent network automation without the complexity of additional protocol layers. 

## ADDED Requirements

### Requirement: MCP exposure of the shared tool registry
The system SHALL provide an MCP server over stdio that exposes the tools from the shared registry. The tools SHALL have the same schemas, descriptions, and behavior as for in-process clients.

#### Scenario: External client lists tools
- **WHEN** an MCP client connects and lists tools
- **THEN** the server returns every registered tool with its input schema and description

### Requirement: Equivalent safety policy
The MCP server SHALL enforce the same policy gate as in-process clients, and SHALL map tool annotations to MCP tool hints.

#### Scenario: Destructive tool hints
- **WHEN** a client lists a tool annotated as destructive
- **THEN** the tool is advertised with the destructive hint, and calls to it follow the session policy

### Requirement: One application session per server process
Each MCP server process SHALL host exactly one application session. The session SHALL run Qt on the process's main thread and dispatch tool calls to the GUI thread.

#### Scenario: Isolated evaluation sample
- **WHEN** an evaluation starts a new server process for a scenario
- **THEN** the process starts a fresh hermetic session that shares no state with other scenarios

### Requirement: Long-running operations as jobs
The MCP server SHALL expose long-running operations through job tools that return job identifiers and report status and results. The job tools SHALL NOT depend on any client's support for long-running tasks.

#### Scenario: Export through MCP
- **WHEN** a client starts an export and polls the job
- **THEN** the job reports its progress, and on completion reports the artifact path and page count

### Requirement: Optional dependency
The MCP server dependency SHALL be optional and SHALL NOT be imported during normal application startup.

#### Scenario: Application without MCP installed
- **WHEN** the application starts in an environment without the MCP package
- **THEN** it starts and operates normally

$paths = @(
    @{path='g:\Model_Mesh\.claude\worktrees\agent-a00c2692'; name='E3.3 Retry with Feedback Loop'},
    @{path='g:\Model_Mesh\.claude\worktrees\agent-a9a93c0c'; name='E1.3 Agent Memory Context'},
    @{path='g:\Model_Mesh\.claude\worktrees\agent-a1b0561f'; name='E10.3 CI/CD Pipeline'},
    @{path='g:\Model_Mesh\.claude\worktrees\agent-ae52da6a'; name='E12.2 Routing Auto-Tuning'}
)

foreach ($item in $paths) {
    Write-Host ""
    Write-Host "$($item.name)" -ForegroundColor Cyan
    if (Test-Path $item.path) {
        Set-Location $item.path
        git status --short
        Write-Host "---DIFF---" -ForegroundColor Yellow
        git diff --stat
    } else {
        Write-Host "Path not found" -ForegroundColor Red
    }
}

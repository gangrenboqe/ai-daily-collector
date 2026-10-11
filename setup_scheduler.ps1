# 简单的计划任务设置脚本
Write-Host "=== AI信息收集计划任务设置 ===" -ForegroundColor Cyan
Write-Host ""

# 检查Python是否可用
try {
    $pythonVersion = python --version
    Write-Host "✅ Python可用: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "❌ Python未安装或未添加到PATH" -ForegroundColor Red
    exit 1
}

# 检查脚本是否存在（路径相对本脚本所在目录，clone 到任何位置都能用）
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath  = Join-Path $scriptDir "ai_daily_scraper.py"
$outDir      = Join-Path $scriptDir "daily"
if (Test-Path $scriptPath) {
    Write-Host "✅ 找到收集脚本: $scriptPath" -ForegroundColor Green
}
else {
    Write-Host "❌ 脚本不存在，请检查路径" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "选择操作:" -ForegroundColor Yellow
Write-Host "1. 创建计划任务（每日9:00运行）" -ForegroundColor Cyan
Write-Host "2. 删除计划任务" -ForegroundColor Cyan
Write-Host "3. 立即运行一次" -ForegroundColor Cyan
Write-Host "4. 测试脚本" -ForegroundColor Cyan
Write-Host "5. 查看任务信息" -ForegroundColor Cyan
Write-Host "q. 退出" -ForegroundColor Gray
Write-Host ""

$choice = Read-Host "请输入选择 (1-5, q)"

switch ($choice) {
    "1" {
        Write-Host "创建计划任务..." -ForegroundColor Green
        
        # 创建任务定义
        $taskName = "DailyAICollector"
        $action = New-ScheduledTaskAction -Execute "python" -Argument "`"$scriptPath`"" `
            -WorkingDirectory "$scriptDir"
        $trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
        $settings = New-ScheduledTaskSettingsSet -Hidden:$false
        
        # 检查任务是否已存在
        try {
            $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($existing) {
                Write-Host "任务已存在，是否重新创建？ (y/n)" -ForegroundColor Yellow
                $confirm = Read-Host
                if ($confirm -ne "y") {
                    Write-Host "已取消" -ForegroundColor Gray
                    break
                }
                # 删除现有任务
                Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            }
        }
        catch {}
        
        # 创建新任务
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
            -Settings $settings -Description "每日收集AI前沿信息" -Force
        
        Write-Host "✅ 计划任务创建成功！" -ForegroundColor Green
        Write-Host "任务名称: $taskName" -ForegroundColor Yellow
        Write-Host "运行时间: 每天上午9:00" -ForegroundColor Yellow
        Write-Host "Python脚本: $scriptPath" -ForegroundColor Yellow
    }
    
    "2" {
        $taskName = "DailyAICollector"
        Write-Host "删除计划任务..." -ForegroundColor Yellow
        
        try {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
            Write-Host "✅ 计划任务 '$taskName' 已删除" -ForegroundColor Green
        }
        catch {
            if ($_.Exception.Message -like "*找不到*") {
                Write-Host "提示：任务 '$taskName' 不存在" -ForegroundColor Yellow
            }
            else {
                Write-Host "❌ 删除失败: $_" -ForegroundColor Red
            }
        }
    }
    
    "3" {
        $taskName = "DailyAICollector"
        Write-Host "立即运行任务..." -ForegroundColor Cyan
        
        try {
            Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
            Write-Host "✅ 任务已启动" -ForegroundColor Green
            Write-Host "请稍后查看输出文件..." -ForegroundColor Yellow
            Write-Host "输出目录: $outDir" -ForegroundColor Yellow
        }
        catch {
            Write-Host "❌ 运行失败: $_" -ForegroundColor Red
            Write-Host "请先创建计划任务（选项1）" -ForegroundColor Yellow
        }
    }
    
    "4" {
        Write-Host "测试脚本..." -ForegroundColor Cyan
        
        try {
            Push-Location $scriptDir
            $output = python "`"$scriptPath`"" 2>&1
            Pop-Location
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ 脚本测试成功" -ForegroundColor Green
                
                # 显示最新文件
                $directory = $outDir
                if (Test-Path $directory) {
                    $files = Get-ChildItem "$directory\*.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 3
                    if ($files) {
                        Write-Host "最新生成的文件:" -ForegroundColor Green
                        foreach ($file in $files) {
                            Write-Host "  • $($file.Name) ($([math]::Round($file.Length/1KB, 2)) KB)" -ForegroundColor Yellow
                        }
                    }
                }
            }
            else {
                Write-Host "❌ 脚本测试失败" -ForegroundColor Red
                Write-Host "错误输出: $output" -ForegroundColor Red
            }
        }
        catch {
            Write-Host "❌ 测试异常: $_" -ForegroundColor Red
        }
    }
    
    "5" {
        $taskName = "DailyAICollector"
        Write-Host "查看任务信息..." -ForegroundColor Cyan
        
        try {
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
            
            Write-Host "=== 任务信息 ===" -ForegroundColor Green
            Write-Host "名称: $($task.TaskName)" -ForegroundColor Yellow
            Write-Host "描述: $($task.Description)" -ForegroundColor Yellow
            Write-Host "状态: $($task.State)" -ForegroundColor Yellow
            
            $info = Get-ScheduledTaskInfo -TaskName $taskName
            Write-Host "最后运行结果: $($info.LastTaskResult)" -ForegroundColor Yellow
            Write-Host "最后运行时间: $($info.LastRunTime)" -ForegroundColor Yellow
            Write-Host "下次运行时间: $($info.NextRunTime)" -ForegroundColor Yellow
            
            # 显示触发器
            Write-Host "触发器:" -ForegroundColor Green
            foreach ($trigger in $task.Triggers) {
                Write-Host "  • $($trigger)" -ForegroundColor Yellow
            }
        }
        catch {
            Write-Host "❌ 获取任务信息失败" -ForegroundColor Red
            Write-Host "错误: $_" -ForegroundColor Red
            Write-Host "可能任务不存在，请先创建（选项1）" -ForegroundColor Yellow
        }
    }
    
    "q" {
        Write-Host "退出" -ForegroundColor Gray
    }
    
    default {
        Write-Host "无效选择" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "操作完成。" -ForegroundColor Cyan
if ($choice -eq "1") {
    Write-Host "提示：您需要以管理员身份运行PowerShell才能创建系统级计划任务。" -ForegroundColor Yellow
}
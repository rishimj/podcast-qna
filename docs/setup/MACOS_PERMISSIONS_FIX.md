# 🍎 macOS Permissions Fix for Daily Cost Reports

## 🚨 **Issue Identified**

Your daily cost reports aren't running because **macOS is blocking automated script execution** due to security restrictions. This is why you didn't get your morning email!

**Error:** `Operation not permitted` when launchd/cron tries to run scripts.

## 🔧 **Solution: Grant Terminal Full Disk Access**

### Step 1: Open System Preferences

1. Click the **Apple menu** → **System Preferences**
2. Click **Security & Privacy**
3. Click the **Privacy** tab

### Step 2: Grant Full Disk Access

1. In the left sidebar, scroll down and select **"Full Disk Access"**
2. Click the **lock icon** 🔒 in the bottom left
3. Enter your **password** to unlock
4. Click the **"+"** button to add an application
5. Navigate to **Applications** → **Utilities** → **Terminal.app**
6. Select **Terminal.app** and click **"Open"**
7. Make sure the checkbox next to **Terminal** is **checked** ✅

### Step 3: Also Add Python (if needed)

1. Still in Full Disk Access, click **"+"** again
2. Navigate to `/Users/rishimanimaran/miniforge3/bin/python3`
3. Select it and click **"Open"**
4. Make sure it's **checked** ✅

### Step 4: Restart Terminal

1. **Quit Terminal completely** (Cmd+Q)
2. **Reopen Terminal**
3. This ensures the new permissions take effect

## 🧪 **Test the Fix**

After granting permissions, test the daily report:

```bash
cd "/Users/rishimanimaran/Documents/Work/podcast-q&a"
./run_daily_report.sh
```

If it works, test the launchd job:

```bash
launchctl start com.podcast-qa.daily-cost-report
```

## 📧 **Alternative Solution: Manual Trigger Script**

If the permissions are still problematic, here's a simple workaround:

### Create a Desktop Shortcut

```bash
# Create a desktop script you can double-click
cat > ~/Desktop/daily_cost_report.command << 'EOF'
#!/bin/bash
cd "/Users/rishimanimaran/Documents/Work/podcast-q&a"
./run_daily_report.sh
echo "Daily cost report completed!"
echo "Press any key to close..."
read -n 1
EOF

chmod +x ~/Desktop/daily_cost_report.command
```

Now you can **double-click** `daily_cost_report.command` on your Desktop anytime!

## 🔄 **Re-setup After Permissions**

Once you've granted permissions, re-run the setup:

```bash
./setup_macos_scheduler.sh
```

## 📊 **Check Current Status**

```bash
# Check if launchd job is loaded
launchctl list | grep podcast-qa

# Check recent logs
tail -20 logs/launchd_out.log
tail -20 logs/launchd_err.log

# Manual cost check
make cost-check
```

## 🎯 **Why This Happened**

- **macOS Catalina+** introduced strict security controls
- **Automated scripts** need explicit permission to access files
- **Terminal** needs "Full Disk Access" to run scripts via launchd/cron
- **Without permission**, scripts fail silently or with "Operation not permitted"

## ✅ **Expected Result**

After fixing permissions:

- ✅ Daily emails will arrive at 10:00 AM
- ✅ No more "Operation not permitted" errors
- ✅ launchd job will run successfully
- ✅ Logs will show successful execution

## 🆘 **If Still Not Working**

Try this alternative approach:

### Option 1: Use Automator

1. Open **Automator**
2. Create new **"Calendar Alarm"**
3. Add **"Run Shell Script"** action
4. Paste: `cd "/Users/rishimanimaran/Documents/Work/podcast-q&a" && ./run_daily_report.sh`
5. Save and set daily alarm

### Option 2: Use Shortcuts App

1. Open **Shortcuts** app
2. Create new shortcut
3. Add **"Run Shell Script"** action
4. Set to run daily via **Automation**

---

## 🎉 **Next Steps**

1. **Grant Terminal Full Disk Access** (most important!)
2. **Test manually** to verify it works
3. **Re-run setup script** to reload launchd job
4. **Wait for tomorrow 10 AM** for automatic email
5. **Check logs** if issues persist

**Your daily AWS cost reports will be back on track!** 📊💰

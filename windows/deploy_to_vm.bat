@echo off
echo ========================================================
echo   ITAM Edge Agent - Deployment to Linux Server
echo ========================================================
echo.

set VM_USER=djezzy
set VM_IP=192.168.1.106
set VM_DIR=/home/djezzy

echo [1/3] Copying Python scripts to %VM_USER%@%VM_IP%:%VM_DIR%...
scp *.py deploy_linux.sh %VM_USER%@%VM_IP%:%VM_DIR%/

echo.
echo [2/3] Copying Server Database Config...
scp configs/agent_config_server_db.json %VM_USER%@%VM_IP%:%VM_DIR%/agent_config.json

echo.
echo [3/3] Deployment script transferred. 
echo To start the services permanently on the VM, please connect via SSH:
echo     ssh %VM_USER%@%VM_IP%
echo Then run:
echo     sudo chmod +x deploy_linux.sh
echo     ./deploy_linux.sh
echo.
pause

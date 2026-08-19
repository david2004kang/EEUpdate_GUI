@ECHO OFF
REM ========================================================================================================== #
REM                                            INTEL CONFIDENTIAL                                              #
REM ========================================================================================================== #
REM                                                                                                            #
REM                                      Copyright 2020 - 2022 Intel Corporation.                              #
REM                                                                                                            #
REM  The source code contained or described herein and all documents related to the source code ("Material")   #
REM  are owned by Intel Corporation or its suppliers or licensors. Title to the Material remains with Intel    #
REM  Corporation or its suppliers and licensors. The Material may contain trade secrets and proprietary and    #
REM  confidential information of Intel Corporation and its suppliers and licensors, and is protected by        #
REM  worldwide copyright and trade secret laws and treaty provisions. No part of the Material may be used,     #
REM  copied, reproduced, modified, published, uploaded, posted, transmitted, distributed, or disclosed in any  #
REM  way without Intel's prior express written permission.                                                     #
REM                                                                                                            #
REM  No license under any patent, copyright, trade secret or other intellectual property right is granted to   #
REM  or conferred upon you by disclosure or delivery of the Materials, either expressly, by implication,       #
REM  inducement, estoppel or otherwise. Any license under such intellectual property rights must be express    #
REM  and approved by Intel in writing.                                                                         #
REM                                                                                                            #
REM  Include any supplier copyright notices as supplier requires Intel to use.                                 #
REM                                                                                                            #
REM  Unless otherwise agreed by Intel in writing, you may not remove or alter this notice or any other notice  #
REM  embedded in Materials by Intel or Intel's suppliers or licensors in any way.                              #
REM                                                                                                            #
REM ==========================================================================================================*/

REM Deleting all the old drivers iqvw<arch>.sys
SET SC=%systemroot%\system32\sc.exe
SET DRV_PATH=%systemroot%\system32\drivers
IF EXIST %DRV_PATH%\iqvw* DEL %DRV_PATH%\iqvw*
CALL %SC% QUERY NAL >nul 2>&1
IF /i %errorlevel% == 0 (
    CALL %SC% STOP NAL >nul 2>&1
    CALL %SC% DELETE NAL >nul 2>&1
)
ECHO [uninstall.bat] Removing iQVW Driver - SUCCESS

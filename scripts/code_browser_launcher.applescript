on run
    set repoDir to "__REPO_DIR__"
    set serverURL to "http://127.0.0.1:8092/"
    set apiURL to "http://127.0.0.1:8092/api/root"
    set selectedFolder to choose folder with prompt "Choose a project folder for Code Browser"
    set folderPath to POSIX path of selectedFolder
    set userID to do shell script "/usr/bin/id -u"
    try
        do shell script "/usr/bin/curl -fsS --max-time 2 " & quoted form of serverURL
    on error
        try
            do shell script "/bin/launchctl kickstart -k gui/" & userID & "/com.gkworks.codebrowser"
        on error
            do shell script "/usr/bin/nohup " & quoted form of (repoDir & "/start.sh") & " " & quoted form of folderPath & " >/tmp/code-browser-launcher.log 2>&1 &"
        end try
        delay 1
    end try
    set escapedPath to my replaceText(folderPath, "\\", "\\\\")
    set escapedPath to my replaceText(escapedPath, "\"", "\\\"")
    set payload to "{\"path\":\"" & escapedPath & "\"}"
    set request to "/usr/bin/curl -fsS --max-time 10 -X POST -H " & quoted form of "Content-Type: application/json" & " -H " & quoted form of "X-Requested-With: CodeBrowser" & " --data " & quoted form of payload & " " & quoted form of apiURL
    try
        do shell script request
    on error errorMessage
        display dialog "Code Browser could not open this folder." & return & errorMessage buttons {"OK"} default button "OK" with icon stop
        return
    end try
    do shell script "/usr/bin/open " & quoted form of serverURL
end run

on replaceText(theText, searchString, replacementString)
    set AppleScript's text item delimiters to searchString
    set textItems to every text item of theText
    set AppleScript's text item delimiters to replacementString
    set replacedText to textItems as text
    set AppleScript's text item delimiters to ""
    return replacedText
end replaceText

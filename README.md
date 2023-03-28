<h2>Analytics BI</h2>

<h2>Requirements</h2>

- python 3.9+
- asyncio
- aiohttp
- websockets
- threading
- psycopg2

Use command *pip3 install -r .\requirements.txt

If pip3 are not installed: sudo apt-install python3-pip

 <h2>How use</h2>
 
 If you run programm from the shell, run it as sudo-user.
 
 If you run programm like a service check yourself.
 
 **To run this programm/script you can use the following commands:**
 
 - Run with opened console. Can't use console for another tasks(console are not available):
  *python3 /path/to/script/main.py*
 - Run with opened console. Can use console for another tasks(console are available):
  *python3 /path/to/script/main.py &*
 - Run like daemon. Console can used for another tasks or can be closed:
  1. Create daemon-file *sudo touch /etc/systemd/system/analytics_bi.service*
  2. Write the following in created daemon-file:
  
   <code>
    
    [Unit]
     Description=Analytics BI
     After=multi-user.target

    [Service]
     Type=idle
     ExecStart=/usr/bin/python3 /path/to/script/main.py
     Restart=always

    [Install]
     WantedBy=multi-user.target
     
   </code>
   
  3. Now start the daemon execute one by one:
  
   - *sudo systemctl daemon-reload*
   - *sudo systemctl enable analytics_bi.service*
   - *sudo systemctl start analytics_bi.service*

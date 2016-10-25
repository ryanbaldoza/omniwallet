from gevent import monkey
monkey.patch_all()

import time
import json, re
from threading import Thread
from flask import Flask, render_template, session, request
from flask.ext.socketio import SocketIO, emit, join_room, leave_room
from msc_apps import *
from balancehelper import *
from omnidex import getOrderbook
import config

app = Flask(__name__)
app.debug = True
app.config['SECRET_KEY'] = config.WEBSOCKET_SECRET
socketio = SocketIO(app)
thread = None
balance = None
clients = 0
maxclients = 0
maxaddresses = 0
addresses = {}
book = {}
lasttrade = 0

def printmsg(msg):
    print msg
    sys.stdout.flush()

def update_book():
    global book, lasttrade
    ret=getOrderbook(lasttrade)
    printmsg("Checking for new orderbook updates, last: "+str(lasttrade))
    if ret['updated']:
      book=ret['book']
      printmsg("Orderbook updated. Lasttrade: "+str(lasttrade)+" Newtrade: "+str(ret['lasttrade'])+" Book length is: "+str(len(book)))
      lasttrade=ret['lasttrade']


def balance_thread():
    """Send balance data for the connected clients."""
    global addresses, maxaddresses, clients, maxclients, book
    count = 0
    TIMEOUT='timeout -s 9 8 '
    while True:
        time.sleep(5)
        count += 1
        printmsg("Tracking "+str(len(addresses))+"/"+str(maxaddresses)+"(max) addresses, for "+str(clients)+"/"+str(maxclients)+"(max) clients, ran "+str(count)+" times")
        #update and push orderbook
        update_book()
        socketio.emit('orderbook',book,namespace='/balance')
        #update and push addressbook
        balances=get_bulkbalancedata(addresses)
        socketio.emit('address:book',
                      balances,
                      namespace='/balance')

@socketio.on('connect', namespace='/balance')
def balance_connect():
    printmsg('Client connected')
    global balance, clients, maxclients
    session['addresses']=[]

    clients += 1
    if clients > maxclients:
      maxclients=clients

    if balance is None:
        balance = Thread(target=balance_thread)
        balance.start()


def endSession(session):
  try:
    global addresses
    for address in session['addresses']:
      if addresses[address] == 1:
        addresses.pop(address)
      else:
        addresses[address] -= 1
  except KeyError:
    #addresses not defined
    printmsg("No addresses list to clean for "+str(session))


@socketio.on('disconnect', namespace='/balance')
def disconnect():
    printmsg('Client disconnected')
    global clients
    clients -=1
    #make sure we don't screw up the counter if reloading mid connections
    if clients < 0:
      clients=0
    endSession(session)


@socketio.on('session:logout', namespace='/balance')
def logout():
    #printmsg('Client logged out')
    endSession(session)


@socketio.on("address:add", namespace='/balance')
def add_address(message):
  global addresses, maxaddresses
  
  address = message['data']
  if str(address) in addresses: 
    addresses[str(address)] += 1
  else:
    addresses[str(address)] = 1

  if str(address) not in session['addresses']:
    session['addresses'].append(str(address))

  if len(addresses) > maxaddresses:
    maxaddresses=len(addresses)

  #speed up initial data load
  balance_data=get_balancedata(address)
  emit('address:'+address,
        balance_data,
        namespace='/balance')

@socketio.on("address:refresh", namespace='/balance')
def refresh_address(message):
  global addresses

  address = message['data']
  if str(address) in addresses:
    balance_data=get_balancedata(address)
    emit('address:'+address,
        balance_data,
        namespace='/balance')
  else:
    add_address(message)

if __name__ == '__main__':
  socketio.run(app, '127.0.0.1',1091)

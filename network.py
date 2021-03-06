import json
import queue
import threading


## wrapper class for a queue of packets
class Interface:
    ## @param maxsize - the maximum size of the queue storing packets
    def __init__(self, maxsize=0):
        self.in_queue = queue.Queue(maxsize)
        self.out_queue = queue.Queue(maxsize)

    ##get packet from the queue interface
    # @param in_or_out - use 'in' or 'out' interface
    def get(self, in_or_out):
        try:
            if in_or_out == 'in':
                pkt_S = self.in_queue.get(False)
                # if pkt_S is not None:
                #     print('getting packet from the IN queue')
                return pkt_S
            else:
                pkt_S = self.out_queue.get(False)
                # if pkt_S is not None:
                #     print('getting packet from the OUT queue')
                return pkt_S
        except queue.Empty:
            return None

    ##put the packet into the interface queue
    # @param pkt - Packet to be inserted into the queue
    # @param in_or_out - use 'in' or 'out' interface
    # @param block - if True, block until room in queue, if False may throw queue.Full exception
    def put(self, pkt, in_or_out, block=False):
        if in_or_out == 'out':
            # print('putting packet in the OUT queue')
            self.out_queue.put(pkt, block)
        else:
            # print('putting packet in the IN queue')
            self.in_queue.put(pkt, block)


## Implements a network layer packet.
class NetworkPacket:
    ## packet encoding lengths
    dst_S_length = 5
    prot_S_length = 1

    ##@param dst: address of the destination host
    # @param data_S: packet payload
    # @param prot_S: upper layer protocol for the packet (data, or control)
    def __init__(self, dst, prot_S, data_S):
        self.dst = dst
        self.data_S = data_S
        self.prot_S = prot_S

    ## called when printing the object
    def __str__(self):
        return self.to_byte_S()

    ## convert packet to a byte string for transmission over links
    def to_byte_S(self):
        byte_S = str(self.dst).zfill(self.dst_S_length)
        if self.prot_S == 'data':
            byte_S += '1'
        elif self.prot_S == 'control':
            byte_S += '2'
        else:
            raise('%s: unknown prot_S option: %s' %(self, self.prot_S))
        byte_S += self.data_S
        return byte_S

    ## extract a packet object from a byte string
    # @param byte_S: byte string representation of the packet
    @classmethod
    def from_byte_S(self, byte_S):
        dst = byte_S[0 : NetworkPacket.dst_S_length].strip('0')
        prot_S = byte_S[NetworkPacket.dst_S_length : NetworkPacket.dst_S_length + NetworkPacket.prot_S_length]
        if prot_S == '1':
            prot_S = 'data'
        elif prot_S == '2':
            prot_S = 'control'
        else:
            raise('%s: unknown prot_S field: %s' %(self, prot_S))
        data_S = byte_S[NetworkPacket.dst_S_length + NetworkPacket.prot_S_length : ]
        return self(dst, prot_S, data_S)




## Implements a network host for receiving and transmitting data
class Host:

    ##@param addr: address of this node represented as an integer
    def __init__(self, addr):
        self.addr = addr
        self.intf_L = [Interface()]
        self.stop = False #for thread termination

    ## called when printing the object
    def __str__(self):
        return self.addr

    ## create a packet and enqueue for transmission
    # @param dst: destination address for the packet
    # @param data_S: data being transmitted to the network layer
    def udt_send(self, dst, data_S):
        p = NetworkPacket(dst, 'data', data_S)
        print('%s: sending packet "%s"' % (self, p))
        self.intf_L[0].put(p.to_byte_S(), 'out') #send packets always enqueued successfully

    ## receive packet from the network layer
    def udt_receive(self):
        pkt_S = self.intf_L[0].get('in')
        if pkt_S is not None:
            print('%s: received packet "%s"' % (self, pkt_S))

    ## thread target for the host to keep receiving data
    def run(self):
        print (threading.currentThread().getName() + ': Starting')
        while True:
            #receive data arriving to the in interface
            self.udt_receive()
            #terminate
            if(self.stop):
                print (threading.currentThread().getName() + ': Ending')
                return



## Implements a multi-interface router
class Router:

    ##@param name: friendly router name for debugging
    # @param cost_D: cost table to neighbors {neighbor: {interface: cost}}
    # @param max_queue_size: max queue length (passed to Interface)
    def __init__(self, name, cost_D, max_queue_size):
        self.stop = False #for thread termination
        self.name = name
        #create a list of interfaces
        self.intf_L = [Interface(max_queue_size) for _ in range(len(cost_D))]
        #save neighbors and interfeces on which we connect to them
        self.cost_D = cost_D    # {neighbor: {interface: cost}}

        # set up the routing table for connected hosts as {destination: {router: cost}}
        self.rt_tbl_D = {neighbor:{self.name: v for k,v in cost_D[neighbor].items()} for neighbor in cost_D}
        self.rt_tbl_D[self.name] = {self.name: 0}
        print('%s: Initialized routing table' % self)
        self.print_routes()


    ## called when printing the object
    def __str__(self):
        return self.name


    ## look through the content of incoming interfaces and
    # process data and control packets
    def process_queues(self):
        for i in range(len(self.intf_L)):
            pkt_S = None
            #get packet from interface i
            pkt_S = self.intf_L[i].get('in')
            #if packet exists make a forwarding decision
            if pkt_S is not None:
                p = NetworkPacket.from_byte_S(pkt_S) #parse a packet out
                if p.prot_S == 'data':
                    self.forward_packet(p,i)
                elif p.prot_S == 'control':
                    self.update_routes(p, i)
                else:
                    raise Exception('%s: Unknown packet type in packet %s' % (self, p))


    ## forward the packet according to the routing table
    #  @param p Packet to forward
    #  @param i Incoming interface number for packet p
    def forward_packet(self, p, i):
        try:
            dst = p.dst

            cfwd = '' # the chosen destination to forward to
            ccost = 999 # the cost of forwarding to the chosen destination

            # if the destination is a neighbor, ensure the packet is forwarded there
            if dst in self.cost_D:
                cfwd = dst
                print("\t" + self.name,"is next to the destination (" + dst + ").",end="")
            else:
                # uses the routing table to find the lowest cost link to forward along
                for router in [key for key in self.cost_D if key.startswith("R")]:
                    cost = self.rt_tbl_D[dst][router] + self.rt_tbl_D[router][self.name]
                    if cost < ccost:
                         ccost = cost
                         cfwd = router
                print("\t" + cfwd,"is lowest-costing next hop to the destination (" + dst + "). ", end="")
            # access the cost vector at the determined out destination and retrieve the interface number
            out = list(self.cost_D[cfwd].keys())[0]
            print("Forward to",cfwd,"along interface",out)

            self.intf_L[out].put(p.to_byte_S(), 'out', True)
            print('%s: forwarding packet "%s" from interface %d to %d' % \
                (self, p, i, out))
        except queue.Full:
            print('%s: packet "%s" lost on interface %d' % (self, p, i))
            pass


    ## send out route update
    # @param i Interface number on which to send out a routing update
    def send_routes(self, i):
        pbody = self.name + json.dumps(self.rt_tbl_D)
        #create a routing table update packet
        p = NetworkPacket(0, 'control', pbody)
        try:
            print('%s: sending routing update "%s" from interface %d' % (self, p, i))
            self.intf_L[i].put(p.to_byte_S(), 'out', True)
        except queue.Full:
            print('%s: packet "%s" lost on interface %d' % (self, p, i))
            pass


    # update the routing tables according to the received distance vector
    # and possibly send out routing updates
    #  @param p Packet containing routing information
    def update_routes(self, p, i):
        print('%s: Received routing update %s from interface %d' % (self, p, i))

        pbody = str(p)
        # determine which router sent the update
        r = pbody[NetworkPacket.dst_S_length+NetworkPacket.prot_S_length:NetworkPacket.dst_S_length+NetworkPacket.prot_S_length+2]
        # extract the distance vector
        rvec = json.loads(pbody[NetworkPacket.dst_S_length+NetworkPacket.prot_S_length+2:])
        keys = self.rt_tbl_D.keys() | rvec.keys() # ensures values that aren't in one of the tables gets considered
        print(keys)
        routers = [key for key in keys if key.startswith("R")]
        print(routers)

        # for each destination listed in the current routing table,
        # update the cost vector at r to the new value
        for dst in keys:
            # if the updated router does not know about the destination, temporarily add it
            if dst not in rvec:
                rvec[dst] = {r: 999}
            # if the current router does not know about the destination, learn about it
            if dst not in self.rt_tbl_D:
                self.rt_tbl_D[dst] = {self.name: 999}

            self.rt_tbl_D[dst][r] = rvec[dst][r]

        # update routers according to Bellman-Ford equation
        updated = False
        for y in keys: # for each possible destination
            for v in routers: # for each possible neighbor
                # destination and neighbor cannot be the same
                if v is y:
                    continue

                ycvec = self.rt_tbl_D[y]
                if v not in ycvec:
                    ycvec[v] = 999
                vcvec = self.rt_tbl_D[v]

                bf = vcvec[self.name] + ycvec[v]
                if bf < ycvec[self.name]:
                    updated = True
                    ycvec[self.name] = bf

        # push update
        if updated:
            for i in range(len(self.intf_L)):
                self.send_routes(i)

    ## Print routing table
    def print_routes(self):
        pstr = '+' # output string
        borderStr = '===+'
        linesepStr = '---+'

        # add top border
        for _ in range(len(self.rt_tbl_D)+1):
            pstr += borderStr
        pstr += '\n|' + self.name + ' |'
        # Add column names
        for k, _ in self.rt_tbl_D.items():
            pstr += " " + k + "|"
        pstr += '\n'

        # add bottom header border
        pstr += "+"
        for _ in range(len(self.rt_tbl_D)+1):
            pstr += borderStr
        pstr += '\n|'

        # add body of table
        count = 0
        for key in self.rt_tbl_D[self.name].keys():
            if count > 0:
                pstr += "+"
                for _ in range(len(self.rt_tbl_D)+1):
                    pstr += linesepStr
                pstr += "\n|"

            pstr += key + " |"
            for _, v in self.rt_tbl_D.items():
                val = 999
                if key in v:
                    val = v[key]
                pstr += str(val).rjust(3) + "|" # rjust necessary here if costs go into double-digits
            pstr += '\n'
            count += 1

        # add bottom border
        pstr += "+"
        for _ in range(len(self.rt_tbl_D)+1):
            pstr += borderStr
        pstr += "\n"

        # print the formatted table
        print(pstr)

    ## thread target for the host to keep forwarding data
    def run(self):
        print (threading.currentThread().getName() + ': Starting')
        while True:
            self.process_queues()
            if self.stop:
                print (threading.currentThread().getName() + ': Ending')
                return

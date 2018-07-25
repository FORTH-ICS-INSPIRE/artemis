//client.js

var PROTO_PATH = __dirname + '/../protogrpc/protos/mservice.proto';
var grpc = require('grpc');
var mservice = grpc.load(PROTO_PATH).mservice;
var io = require('socket.io-client');
var socket = io.connect('http://stream-dev.ris.ripe.net', {path: '/stream/socket.io/'});
var client = new mservice.MessageListener('localhost:50051',
                                       grpc.credentials.createInsecure());
var ArgumentParser = require('argparse').ArgumentParser;
var parser = new ArgumentParser({
    version: '0.0.1',
    addHelp: true,
    description: 'RIPE RIS Monitor Client'
});
var ip6addr = require('ip6addr');

parser.addArgument(
    [ '-p', '--prefix' ],
    {
        help: 'Prefix to be monitored',
        defaultValue: null
    }
);
parser.addArgument(
    [ '-r', '--host' ],
    {
        help: 'RRC host',
        defaultValue: null
    }
);

var args = parser.parseArgs();
var sublist = args.prefix.split('/');
var subnet = ip6addr.createCIDR(sublist[0], parseInt(sublist[1]));

socket.on('ris_message', function(msg) {
    var recv_pref = msg['prefix'].split('/')
    if(subnet.contains(recv_pref[0]) && parseInt(recv_pref[1]) >= parseInt(sublist[1])) {
        json_obj = {
            'timestamp': msg['timestamp'],
            'prefix': msg['prefix'],
            'service': 'RIPEris '.concat(msg['host']),
            'as_path': msg['path'],
            'community': msg['community'],
            'type': msg['type'],
        };

        client.queryMformat(json_obj, function(err, response) {
            if(err)
                console.log(err);
        });
    }
});

socket.emit('ris_subscribe',
{
    "prefix": args.prefix,
    "origin": null,
    "type": null,
    "moreSpecific": true,
    "lessSpecific": false,
    "includeBody": false,
    "host": args.host,
    "peer": null
});

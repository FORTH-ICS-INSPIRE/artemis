//client.js

var PROTO_PATH = __dirname + '/../protogrpc/protos/service.proto';
var grpc = require('grpc');
var service = grpc.load(PROTO_PATH).service;
var io = require('socket.io-client');
var socket = io.connect('http://stream-dev.ris.ripe.net', {path: '/stream/socket.io/'});
var client = new service.MessageListener('localhost:50051',
                                       grpc.credentials.createInsecure());
var ArgumentParser = require('argparse').ArgumentParser;
var parser = new ArgumentParser({
    version: '0.0.1',
    addHelp: true,
    description: 'Argparse example'
});

parser.addArgument(
    [ '-p', '--prefix' ],
    {
        help: 'Prefix to be monitored',
        defaultValue: null
    }
);
parser.addArgument(
    [ '-r', '--rrc' ],
    {
        help: 'RRC host',
        defaultValue: null
    }
);

var args = parser.parseArgs();

socket.on('ris_message', function(msg) {
    json_obj = {
        'timestamp': msg['timestamp'],
        'prefix': msg['prefix'],
        'service': 'RIPEris '.concat(msg['host']),
        'as_path': msg['path'],
        'type': msg['type'],
        'origin_as': msg['peer_asn'],
    };

    client.queryPformat(json_obj, function(err, response) {
        if(err)
	       console.log(err);
    });
});

socket.emit('ris_subscribe', 
{
    "prefix": args.prefix,
    "origin": null,
    "type": null,
    "moreSpecific": true,
    "lessSpecific": false,
    "includeBody": false,
    "host": args.rrc,
    "peer": null
});

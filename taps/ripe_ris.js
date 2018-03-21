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
    description: 'RIPE RIS Monitor Client'
});

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

var ip2long = function(ip){
    var components;

    if(components = ip.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/))
    {
        var iplong = 0;
        var power  = 1;
        for(var i=4; i>=1; i-=1)
        {
            iplong += power * parseInt(components[i]);
            power  *= 256;
        }
        return iplong;
    }
    else return -1;
};

var inSubNet = function(ip, subnet)
{   
    var mask, base_ip, long_ip = ip2long(ip);
    if( (mask = subnet.match(/^(.*?)\/(\d{1,2})$/)) && ((base_ip=ip2long(mask[1])) >= 0) )
    {
        var freedom = Math.pow(2, 32 - parseInt(mask[2]));
        return (long_ip > base_ip || long_ip === base_ip) && 
            ((long_ip < base_ip + freedom - 1) || (long_ip === base_ip + freedom - 1));
    }
    else return false;
};

socket.on('ris_message', function(msg) {
    if(inSubNet(msg['prefix'].split('/')[0], args.prefix)){
        json_obj = {
            'timestamp': msg['timestamp'],
            'prefix': msg['prefix'],
            'service': 'RIPEris '.concat(msg['host']),
            'as_path': msg['path'],
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

var io = require('socket.io').listen(8020)
, fs = require('fs')
, redis = require('redis');

var sub = redis.createClient();
io.set('log level', 1)
sub.subscribe("all")
var cache_size = 2000;
var cached = [];

function append_to_cache(key) {
    if (cached.length >= cache_size) {
	cached.pop();
    }
    cached.unshift(key);
}

sub.on("message", function(channel, key) {
    append_to_cache(key);
})
io.sockets.on('connection', function (socket) {
    sub.on("message", function(channel, key) {
	socket.emit('news', key);
    })
    socket.on('give', function (n) {
	n = parseInt(n, 10);
	for (var i=n;i>=0;i--) {
            socket.emit('given', cached[i]);
	}
    })
})

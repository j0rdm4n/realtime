$(document).ready(function () {
    var insert = function ($elem) {
	$children = $events.children();
	if ($children.size() > max_events ) {
	    $children.last().remove();
	}
	$elem
	    .hide()
	    .prependTo($events)
	    .slideDown('slow');
    }
    var $events = $('.events');
    var max_events = 10;
    var ej = new EJS({'url':'/static/js/templates/index.ejs'});
    EJS.config({'cache':false});
    socket.on('given', function (data) {
	render(data).hide().prependTo($events).slideDown();
    });
    var render = function (data) {
	var event = $.parseJSON(data);
	event.imgsrc = 'http://www.gravatar.com/avatar/'+event.gravatar_id+'?s='+gravatar_size+'&d='+gravatar_default;
	return $(ej.render(event))
    };
    socket.on('news', function (data) {
	var $elem = render(data);
	console.log($elem);
	// turn into msec
	var delay_size = event.query_delay / event.len_events;
	var delay = delay_size * event.i * 1000;
	console.log(delay);
	console.log(event.got_img);
	// wait until the image is ready and then
	// set the timeout to delay it into the DOM
	$elem.waitForImages({
	    finished: function () {
		setTimeout(insert, delay, $elem);
	    },
	    waitForAll: true,
	})
    })
    socket.emit('give', max_events);
})

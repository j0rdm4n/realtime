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
	var event = $.parseJSON(data);
	console.log(event);
	$(ej.render(event)).hide().prependTo($events).slideDown();
    })
    socket.on('news', function (data) {
	var event = $.parseJSON(data);
	var $elem = $(ej.render(event));
	console.log($elem);
	// turn into msec
	var delay_size = event.query_delay / event.len_events;
	var delay = delay_size * event.i * 1000;
	console.log(delay);
	console.log(event.got_img);
	setTimeout(insert, delay, $elem);
    })
    socket.emit('give', max_events);
})

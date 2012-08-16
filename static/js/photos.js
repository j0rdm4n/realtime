$(document).ready(function () {
    var $photos = $('.photos');
    var max_containers = 20;
    var ej = new EJS({'url':'/static/js/templates/photo.ejs'});
    var insert = function () {
	var $container = $('<div class="container"></div>')
	var max_children = 5;
	return function ($elem) {
	    if ($container.children().size() === max_children) {
		//.hide()
		//.slideDown('slow');
		$container = $('<div class="container"></div>')
		$container.append($elem);
		$container.hide().prependTo($photos).slideDown();
		console.log('new container');
	    } else {
		$container.append($elem);
	    }
	    $containers = $photos.children();
	    if ($containers.size() > max_containers ) {
		$containers.last().remove();
	    }
	}
    }()
    var news = function (data) {
	if (!run)
	    return;
	var event = $.parseJSON(data);
	event.lang = event.lang || '_';
	if (!event.got_img)
	    return;
	var $elem = $(ej.render(event));
	console.log($elem);
	// turn into msec
	var delay_size = event.query_delay / event.len_events;
	var delay = delay_size * event.i * 1000;
	console.log(delay);
	console.log(event.got_img);
	setTimeout(insert, delay, $elem);
    }
    socket.on('given', news)
    socket.emit('give', 50);
    socket.on('news', news)
})

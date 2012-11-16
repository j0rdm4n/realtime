Realtime
========

Realtime visualizes GitHub activity in real time. 

The architecture works as follows:

* A celery instance kicks off a ``scrape`` task every second which queries the GitHub API endpoint at ``https://github.com/timeline.json``. A human-readable string of the event is generated ``A forked repository B from C/B`` with a link to A/B. That JSON object is then sent to a Redis Pub/Sub which is consumed by

* a small NodeJS instance with Socket.IO which pushes the live data to all connected clients. It also caches a couple hundred events so clients can "pre-load" events to fill their screen upon first connecting.

* The front-end then has 2 views of said data-stream

  - One is to simply display a global "list-view" of all events that describes what's happening.

  - Another is one that queries all available gravatars (this used to happen on the server until gravatar banned my server IP) and simply lists the event's ``author``'s avatar along with the programming language associated with the event. ``This allows you to efficiently reduce every programmer to their physical appearance and choice of programming language.``

Please note that the live web app at http://realtime.doda.co/ is currently offline. It was fun to demo this to fellow dev buddies while I was building it, though I don't really see a reason to run 3,600 requests / hour against GitHub's API just for the fun of it.
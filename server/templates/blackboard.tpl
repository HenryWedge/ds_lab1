                    <div id="boardcontents_placeholder">
                    <div class="row">
                    <!-- this place will show the actual contents of the blackboard. 
                    It will be reloaded automatically from the server -->
                        <div class="card shadow mb-4 w-100">
                            <div class="card-header py-3">
                                <h6 class="font-weight-bold text-primary">Blackboard content</h6>
                            </div>
                            <div class="card-body">
                                <input type="text" name="id" value="ID" readonly>
                                <input type="text" name="entry" value="Entry" size="70%%" readonly>
                                <input type="text" name="clock" value="Clock" size="20%%" readonly>
                                % for entry in board_dict:
                                    <form class="entryform" target="noreload" method="post" action="/board/{{entry.id}}/propagate">
                                        <input type="text" name="id" value="{{entry.id}}" readonly disabled> <!-- disabled field won’t be sent -->
                                        <input type="text" name="entry" value="{{entry.entry}}" size="70%%">
                                        <input type="text" name="clock" value="{{entry.clock}}" readonly disabled>
                                        <button type="submit" name="delete" value="0">Modify</button>
                                        <button type="submit" name="delete" value="1">X</button>
                                    </form>
                                %end
                            </div>
                        </div>
                    </div>
                    </div>
                    <div id="boardcontents_placeholder">
                    <div class="row">
                    <!-- this place will show the actual contents of the blackboard.
                    It will be reloaded automatically from the server -->
                        <div class="card shadow mb-4 w-100">

                            <div class="card-body">
                            % for id, value in board_dict['accept']:
                                <form class="entryform" target="noreload" method="post" action="/signrequest/answer/{{id}}">
                                    <input type="text" name="name" value={{value.diploma.name}} readonly>
                                    <input type="text" name="subject" value={{value.diploma.subject}} readonly>
                                    <input type="text" name="grade" value={{value.diploma.grade}} readonly>
                                    <button type="submit" name="accept" value="1">Accept</button>
                                    <button type="submit" name="accept" value="0">Reject</button>
                                </form>
                            %end
                            </div>

                            <div class="card-header py-3">
                                <h6 class="font-weight-bold text-primary">Blackboard content</h6>
                            </div>

                            <div class="card-body">
                                <input type="text" name="id" value="ID" readonly>
                                <input type="text" name="name" value="Name" size="30%%" readonly>
                                <input type="text" name="subject" value="Subject" size="20%%" readonly>
                                <input type="text" name="grade" value="Grade" size="20%%" readonly>
                                <input type="text" name="blockhash" value="BlockHash" size="20%%" readonly>
                                % for board_entry, board_element in board_dict['data']:
                                    <form class="entryform" target="noreload" method="post" action="/board/{{board_entry}}/propagate">
                                        <input type="text" name="id" value="{{board_entry}}" readonly disabled> <!-- disabled field won’t be sent -->
                                        <input type="text" name="name" value="{{board_element[0].name}}" size="30%%" readonly disabled>
                                        <input type="text" name="subject" value="{{board_element[0].subject}}" size="20%%" readonly disabled>
                                        <input type="text" name="grade" value="{{board_element[0].grade}}" size="20%%" readonly disabled>
                                        <input type="text" name="blockhash" value="{{board_element[1]}}" size="20%%" readonly disabled>
                                    </form>
                                %end
                            </div>
                        </div>
                    </div>
                    </div>

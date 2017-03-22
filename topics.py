content_move = (
        'topic: ~move_topic()\n'
        'language: enu\n'

        'concept: (direction) [forward back left right]\n'

        'u:(move _~direction) I will move $1 $moveDir=$1\n'
        
        'u:(who am i) $reply=1\n'

        'u:(follow me) $follow=1\n'
        'u:(stop) $follow=0\n'

        'u:(bye) bye $animate=1\n'

        'u: (test two) hello from second topic\n'
    )
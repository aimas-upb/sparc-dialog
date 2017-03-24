content_move = (
    'topic: ~move_topic()\n'
    'language: enu\n'

    'concept: (direction) [forward back left right]\n'

    'u:(move _~direction) $MoveDirectionEvent=$1\n'


    'u:(hello) Hy there\n'
    'u:(how are you) I am fine, thanks\n'


    'u:(what is my name) $WhoAmIEvent=1\n'

    'u:(follow me) $FollowEvent=1\n'
    'u:(stop) $FollowEvent=0\n'
    'u:(stop following me) $FollowEvent=0\n'

    'u:(bye) bye $AnimationEvent=1\n'
)

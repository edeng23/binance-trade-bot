import React from 'react';
import styled from "styled-components";
import Coffee from "./CoffeeButton";
import dogeCoin from 'cryptocurrency-icons/128/color/doge.png'
import coin2 from 'cryptocurrency-icons/128/color/meetone.png'
import coin3 from 'cryptocurrency-icons/128/color/bcbc.png'

type Props = {};

const HomePage: React.FC<Props> = (props: Props) => {
    return (
        <Wrapper>
            <Coins>
                <img height={128} width={128} alt={'icon'} src={dogeCoin}/>
                <img height={128} width={128} alt={'icon'} src={coin2}/>
                <img height={128} width={128} alt={'icon'} src={coin3}/>
            </Coins>
            <Header>Welcome to the crypto bot! your more then welcome to:</Header>
            <Coffee/>
        </Wrapper>

    );
}

export default HomePage;

const Wrapper = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  margin-bottom: 6%;
`;

const Header = styled.h1`
  margin-bottom: 1em;
`;


const Coins = styled.div``;